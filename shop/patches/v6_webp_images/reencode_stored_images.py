"""Re-encode the storefront images already uploaded to WebP.

Runs post_model_sync, after v5_public_images has put them in public storage.
Without this the uploader fix only helps from the next upload onwards, and the
files that prompted it keep their size: nine product photos sitting at
519-988KB, which is what a lossless PNG of a photograph costs.

The encode is not repeated here. It calls the same `shrink_uploaded_image` the
uploader hook uses, so a file already on disk goes through exactly the path a new
upload would, with the same rules: cap at 800px, offer WebP and the source
format, keep the smaller, discard anything heavier than the original, skip
animations. That reuse is the point - a second implementation would be a second
set of bugs.

What this patch adds is everything the uploader never had to deal with, because
for a new upload nothing references the file yet. Here the bytes are on disk, a
File row describes them and doctypes point at them, so:

  - `File.file_url`/`file_name`/`file_type` are corrected to the new name and
    format. `shrink_uploaded_image` sets them on the doc; saving persists them.
  - `File.content_hash` is recomputed. It is how Frappe recognises the same bytes
    uploaded twice and it is derived from the content, so a stale hash after a
    re-encode would fingerprint the new file with the old file's identity.
  - File rows left naming bytes that no longer exist are pointed at a surviving
    row for the same content. The same image uploaded twice is two rows
    describing one file, and converting one of them deletes the bytes out from
    under the other.
  - Every field pointing at the old url is repointed, matched per file rather
    than by a blanket prefix replace, so a file this run did not convert is left
    exactly as it is.

Re-running is a no-op: the converted files are already WebP, the encode declines
to touch a file it cannot make smaller, and nothing is left orphaned. Because the
orphan repair is its own pass rather than part of the conversion, it also
finishes a job a previous run started and did not complete.
"""

import os

import frappe

from shop.files import (
	RESIZABLE,
	extension,
	set_image_reference,
	shrink_uploaded_image,
	site_file_path,
	storefront_image_references,
)

PUBLIC_PREFIX = "/files/"
# Below this there is nothing to win. The smallest storefront image is a few
# hundred bytes of QR code, and WebP is larger than those - which is exactly why
# the encode is measured per file rather than applied by rule.
WORTH_ENCODE_ABOVE = 8 * 1024


def execute() -> None:
	report = reencode_stored_images()
	if report["converted"] or report["repaired"]:
		frappe.msgprint(
			f"reloop: re-encoded {len(report['converted'])} storefront image(s) to WebP,"
			f" repaired {len(report['repaired'])} duplicate row(s)"
			f"{_skipped_note(report['skipped'])}",
			alert=True,
		)


def reencode_stored_images() -> dict:
	"""Convert what is worth converting, and describe it. Split out to dry-run."""
	references = storefront_image_references(PUBLIC_PREFIX)
	converted: list[dict] = []
	skipped: list[str] = []

	for old_url in sorted(references):
		basename = old_url.rsplit("/", 1)[-1]
		if extension(old_url) not in RESIZABLE:
			continue

		path = site_file_path(old_url)
		if not path or not os.path.isfile(path):
			skipped.append(f"{basename}: no File row or not on disk")
			continue

		if os.path.getsize(path) < WORTH_ENCODE_ABOVE:
			skipped.append(f"{basename}: {os.path.getsize(path):,} bytes, not worth opening")
			continue

		rows = frappe.get_all("File", filters={"file_url": old_url}, pluck="name")
		if not rows:
			skipped.append(f"{basename}: no File row")
			continue

		for name in rows:
			doc = frappe.get_doc("File", name)
			new_url, old_hash = _reencode(doc)
			if not new_url or new_url == old_url:
				skipped.append(f"{basename}: nothing gained, left as is")
				continue
			converted.append(
				{"name": name, "from": old_url, "to": new_url, "old_hash": old_hash}
			)
			for table, selector, fieldname in references[old_url]:
				set_image_reference(table, selector, fieldname, new_url)

	repaired = _repair_orphans(skipped)

	frappe.clear_document_cache("File")
	return {"converted": converted, "repaired": repaired, "skipped": skipped}


def _reencode(doc) -> tuple[str | None, str | None]:
	"""Run the uploader's encode over an existing File. Returns (new url, old hash).

	`shrink_uploaded_image` moves the bytes and rewrites file_url, file_name,
	file_type and file_size on the doc, so the doc is saved afterwards to persist
	them. The original has already been unlinked by then.

	The old hash is returned rather than stashed on the doc, because the caller
	needs it after the fact and anything left on `doc.flags` is gone by the time
	the next step re-reads the row.
	"""
	before = doc.file_url
	old_hash = doc.content_hash

	shrink_uploaded_image(doc)
	if doc.file_url == before:
		return None, old_hash

	_rehash(doc)
	doc.save()
	return doc.file_url, old_hash


def _rehash(doc) -> None:
	"""Recompute the content hash, which is derived from the bytes just changed.

	`generate_content_hash` only fills a falsy hash, so it has to be cleared
	first - assigning the new value directly would need the file read here
	instead, and this way the reading stays in one place.
	"""
	doc.content_hash = None
	doc.generate_content_hash()


def _repair_orphans(skipped: list[str]) -> list[str]:
	"""Point File rows whose bytes are gone at a surviving row for the same bytes.

	Running this as its own pass, rather than only for the files this run just
	converted, is what makes the patch able to finish a job it already started.
	The same image uploaded twice is two File rows describing one set of bytes and
	Frappe keeps them in step by content hash; converting one row breaks that
	link, because the move deletes the shared bytes and the sibling is left naming
	a file that no longer exists. Doing it as a pass also means a run that was
	interrupted half way is repaired by the next one, rather than needing the
	original upload to be repeated.

	Only rows that are actually broken are touched - one whose file is still on
	disk is fine, and repointing it would orphan a file nothing has deleted.
	"""
	repaired = []
	for row in frappe.get_all(
		"File",
		filters={"file_url": ["like", f"{PUBLIC_PREFIX}%"], "is_folder": 0},
		fields=["name", "file_url", "content_hash"],
	):
		name, file_url = row["name"], row["file_url"]
		orphan_path = site_file_path(file_url or "")
		if orphan_path and os.path.isfile(orphan_path):
			continue
		if not row["content_hash"]:
			skipped.append(f"{name}: file missing and no content hash to match on")
			continue

		# A row for the same bytes whose file is actually present.
		donor = _find_donor(name, row["content_hash"], file_url)
		if not donor:
			# The bytes are gone and nothing describes them. Reported, never
			# invented: a customer needs to be told their photo is missing.
			skipped.append(f"{name}: file missing and no surviving copy of those bytes")
			continue

		orphan = frappe.get_doc("File", name)
		orphan.file_url = donor["file_url"]
		orphan.file_name = os.path.basename(donor["file_url"])
		orphan.file_type = donor["file_type"]
		orphan.file_size = donor["file_size"]
		orphan.content_hash = donor["content_hash"]
		orphan.save()
		repaired.append(f"{name} -> {donor['file_url']}")
	return repaired


def _find_donor(name: str, content_hash: str, file_url: str) -> dict | None:
	"""The row that now holds these bytes, or None.

	Two ways to find it, in order of how much they can be trusted:

	By content hash. That is the real link - same bytes. It is also the one that
	is gone by the time this runs, because the row that was converted was
	re-hashed against its new contents, so a sibling left behind no longer shares
	a hash with anything.

	By filename stem, as a fallback for exactly that case. A conversion renames a
	file by swapping its extension and nothing else, so `photo.png` becoming
	`photo.webp` means the stem still matches, and that is a relationship the
	conversion itself created rather than a coincidence. Guarded: more than one
	candidate means the name is genuinely ambiguous and nothing is guessed.
	"""
	by_hash = [
		row
		for row in frappe.get_all(
			"File",
			filters={"content_hash": content_hash, "name": ["!=", name]},
			fields=["name", "file_url", "file_type", "file_size", "content_hash"],
		)
		if (p := site_file_path(row["file_url"] or "")) and os.path.isfile(p)
	]
	if len(by_hash) == 1:
		return by_hash[0]
	if by_hash:
		return None

	stem = os.path.splitext(os.path.basename(file_url))[0]
	if not stem:
		return None
	by_stem = [
		row
		for row in frappe.get_all(
			"File",
			filters={"name": ["!=", name], "file_url": ["like", f"%/{stem}.%"]},
			fields=["name", "file_url", "file_type", "file_size", "content_hash"],
		)
		if os.path.splitext(os.path.basename(row["file_url"]))[0] == stem
		and (p := site_file_path(row["file_url"] or ""))
		and os.path.isfile(p)
	]
	return by_stem[0] if len(by_stem) == 1 else None


def _skipped_note(skipped: list[str]) -> str:
	return f", skipped {len(skipped)}" if skipped else ""
