"""Make storefront images publicly readable.

Runs post_model_sync. Nothing here changes what the shop sells or what a file
looks like - it only changes who is allowed to read it.

Frappe's file uploader defaults every `Attach Image` upload to private:

    private: !props.make_attachments_public || !frappe.utils.can_upload_public_files()

`make_attachments_public` is read from the DocType (and `make_attachment_public`
from the field), and neither was set on the three doctypes holding images the
public can see. So every product photo, collection tile and the store logo was
written under `private/files/` and handed to visitors as a `/private/files/...`
url. A guest asking for one of those gets 403, so the storefront rendered broken
images while the files sat on disk intact and the upload reported success.

The move is two steps and both are needed:

  1. Flipping `File.is_private` to 0 makes Frappe move the file to `public/files/`
     and rewrite `File.file_url`. It does NOT touch the doctypes that *point* at
     the file - `update_existing_file_docs` only syncs other File rows that share
     the content hash. Left alone, every reference keeps the old `/private/files/`
     url and still 403s.
  2. So the references are rewritten here to follow the files step 1 moved. A
     blanket `/private/` -> `/files/` replace would be shorter and wrong: it
     would repoint a field at a public file that was never moved, and 404 rather
     than quietly working.

Only files these fields actually reference are touched, and only the ones that
are really private. A url with a subfolder in it is skipped and reported, because
Frappe's `handle_is_private_changed` moves on the basename alone and would drop
the nested file in the wrong directory.

Note that one flip can move several File rows: rows sharing a content hash are the
same bytes uploaded twice, and Frappe keeps their urls in step. So the files are
looked up by basename rather than by exact url, which is what that dedup would
otherwise break.

Re-running is a no-op.
"""

import frappe

# Fields a guest's browser is handed, as (doctype, fieldname) on a document.
# Shop Settings is a Single, so it has no table and is read and written through
# the Singles helpers rather than get_all/set_value. Handled by is_single().
DOCUMENT_FIELDS = [
	("Shop Collection", "image"),
	("Shop Settings", "store_logo"),
]

# Fields behind a child table, as (parent doctype, table field, child doctype, child field).
CHILD_FIELDS = [
	("Shop Product", "images", "Shop Product Image", "image"),
]

PRIVATE_PREFIX = "/private/files/"
PUBLIC_PREFIX = "/files/"


def execute() -> None:
	"""Move every guest-facing image to public storage and follow it there."""
	report = make_stored_images_public()
	if report["moved"]:
		frappe.msgprint(
			f"reloop: made {len(report['moved'])} storefront image(s) public"
			f"{_skipped_note(report['skipped'])}",
			alert=True,
		)


def make_stored_images_public() -> dict:
	"""Do the work and describe it. Split from execute() so it can be dry-run.

	Returns {"moved": [file names], "skipped": [reason strings]}."""
	references = _private_references()
	if not references:
		return {"moved": [], "skipped": []}

	moved: list[str] = []
	skipped: list[str] = []

	for basename in sorted({url.rsplit("/", 1)[-1] for url in references}):
		# Frappe moves on the basename alone, so a nested url would be flattened
		# into public/files/ and the reference would point at a path that is not
		# where the file landed. Only the part after the prefix decides this:
		# "/private/files/a.png" has three slashes of its own and is not nested.
		nested = [url for url in references if "/" in url.removeprefix(PRIVATE_PREFIX)]
		if nested:
			skipped.append(f"{basename}: nested in a subfolder, needs a manual move")
			continue

		rows = frappe.get_all("File", filters={"file_url": ["like", f"%/{basename}"]}, pluck="name")
		if not rows:
			skipped.append(f"no File row for {basename}")
			continue

		flipped = _make_public(rows)
		moved.extend(flipped)

	_repoint_references(references)

	return {"moved": moved, "skipped": skipped}


def _is_single(doctype: str) -> bool:
	"""True for a Single doctype, which has no table of its own.

	Shop Settings holds the store logo and is one of these, so asking the database
	for a `tabShop Settings` table raises rather than returning nothing.
	"""
	return bool(frappe.db.get_value("DocType", doctype, "issingle"))


def _private_references() -> dict:
	"""Map every referenced `/private/files/...` url to the rows holding it.

	Each entry is (table, row selector, fieldname), so a rewrite later can name
	the exact row rather than pattern-matching a string across the whole table.
	"""
	references: dict[str, list[tuple[str, dict, str]]] = {}

	for doctype, fieldname in DOCUMENT_FIELDS:
		if not frappe.db.exists("DocType", doctype):
			continue
		if _is_single(doctype):
			url = frappe.db.get_single_value(doctype, fieldname)
			if url and url.startswith(PRIVATE_PREFIX):
				references.setdefault(url, []).append((doctype, {"doctype": doctype}, fieldname))
			continue
		for row in frappe.db.get_all(
			doctype,
			fields=["name", fieldname],
			filters={fieldname: ["like", f"{PRIVATE_PREFIX}%"]},
		):
			if row.get(fieldname):
				references.setdefault(row[fieldname], []).append(
					(doctype, {"name": row["name"]}, fieldname)
				)

	for _, _, child, child_field in CHILD_FIELDS:
		if not frappe.db.exists("DocType", child):
			continue
		for row in frappe.db.get_all(
			child,
			fields=["name", child_field],
			filters={child_field: ["like", f"{PRIVATE_PREFIX}%"]},
		):
			if row.get(child_field):
				references.setdefault(row[child_field], []).append(
					(child, {"name": row["name"]}, child_field)
				)

	return references


def _make_public(file_names: list[str]) -> list[str]:
	"""Flip the given File rows to public. Returns the rows actually moved.

	One basename can be several File rows: the same bytes uploaded twice share a
	content hash, and Frappe rewrites every row sharing it. Flipping one is
	enough, and flipping them all is still correct.
	"""
	moved = []
	for name in file_names:
		doc = frappe.get_doc("File", name)
		if not doc.is_private:
			continue
		doc.is_private = 0
		doc.save()  # moves on disk, rewrites this row's file_url
		moved.append(name)
	return moved


def _repoint_references(references: dict) -> None:
	"""Point every referencing row at where its file now lives.

	Decided from the File row's current state rather than from what this run
	moved, so a run interrupted between the move and the rewrite repairs itself
	instead of leaving fields on a /private/ url whose file is already public -
	which is the one state that 403s while looking correct in the database.

	Matching is per-file, so a field holding a file that is still private keeps
	its url and its 403: honest, and visible in the report, rather than a
	silently 404ing repoint at a file that was never moved.
	"""
	for old_url, rows in references.items():
		basename = old_url.rsplit("/", 1)[-1]
		still_private = frappe.db.exists(
			"File", {"file_url": ["like", f"%/{basename}"], "is_private": 1}
		)
		if still_private:
			continue

		new_url = f"{PUBLIC_PREFIX}{basename}"
		if new_url == old_url:
			continue
		for table, selector, fieldname in rows:
			if _is_single(table):
				frappe.db.set_single_value(table, fieldname, new_url, update_modified=False)
				continue
			frappe.db.set_value(
				table, selector, fieldname, new_url, update_modified=False
			)


def _skipped_note(skipped: list[str]) -> str:
	return f", skipped {len(skipped)}" if skipped else ""
