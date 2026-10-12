"""Image upload hygiene for storefront performance.

Demo images are capped at 800px, but phone uploads arrive at full sensor size
and would undo that work. This shrinks new image uploads in place during
File.before_insert, i.e. before the file is ever served, so URLs, caches and
every upload path (desk forms, front-end uploader, API) stay consistent.

Format is chosen too, because resizing alone left the worst offenders alone: a
PNG of a photograph stays a PNG however many times it is re-encoded, and those
were arriving at 800-990KB. WebP is about 97% smaller on the same pixels here.
The extension follows the format, which is safe at this point in the lifecycle:
the upload response carries `file_url` and the attach control sets the field from
that response (`on_upload_complete` -> `set_value`), so nothing points at the old
name yet.

Which format actually wins is measured, not assumed. A WebP and a same-family
encode are both written and the smaller kept, so a source WebP handles badly
stays what it was, and a re-encode that came out heavier than the upload is
discarded rather than kept as a regression.

Anything non-image, animated, vector-based, outside the site folders (app
assets, external urls) or already within bounds is left untouched, and any
failure leaves the original file alone - an upload must never break.
"""

import os
import re
import tempfile

import frappe
from frappe.utils.data import strip_html
from PIL import Image, ImageOps

MAX_DIM = 800  # same cap as the re-encoded demo set
QUALITY = 75  # JPEG fallback quality, unchanged
WEBP_QUALITY = 82
RECOMPRESS_ABOVE = 150 * 1024  # heavy-but-small-dimension jpeg/webp still re-encoded

RESIZABLE = {"jpg", "jpeg", "png", "webp"}
# The same-family encode offered alongside WebP, so a source WebP cannot improve
# on still keeps its own format. PNG is the case that actually matters: it is a
# lossless container being asked to hold a photograph.
FAMILY = {"jpg": "JPEG", "jpeg": "JPEG", "png": "PNG", "webp": "WEBP"}
SUFFIX = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}
CONTENT_TYPE = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}

# The fields holding an image a guest's browser is handed, as (doctype, fieldname)
# on a document, and (parent doctype, table field, child doctype, child field)
# behind a child table. One list, because two things have to agree on it exactly:
# the migrations that fix files already uploaded, and anyone adding an image field
# later who needs to know it has to be added here too.
STOREFRONT_IMAGE_FIELDS = [
	("Shop Collection", "image"),
	("Shop Settings", "store_logo"),
]
STOREFRONT_CHILD_IMAGE_FIELDS = [
	("Shop Product", "images", "Shop Product Image", "image"),
]


def is_single(doctype: str) -> bool:
	"""True for a Single doctype, which has no table of its own.

	Shop Settings holds the store logo and is one, so asking the database for a
	`tabShop Settings` table raises rather than returning nothing.
	"""
	return bool(frappe.db.get_value("DocType", doctype, "issingle"))


def storefront_image_references(prefix: str | None = None) -> dict:
	"""Map each url held by a storefront image field to the rows holding it.

	`prefix` narrows the map to urls starting with it - `/private/` to find the
	files still filed privately, `/files/` to find the ones already moved.

	Each entry is (table, row selector, fieldname), so a rewrite can name the
	exact row rather than pattern-matching a string across a whole table.
	"""
	references: dict[str, list[tuple[str, dict, str]]] = {}

	def keep(url):
		return bool(url) and (prefix is None or url.startswith(prefix))

	for doctype, fieldname in STOREFRONT_IMAGE_FIELDS:
		if not frappe.db.exists("DocType", doctype):
			continue
		if is_single(doctype):
			url = frappe.db.get_single_value(doctype, fieldname)
			if keep(url):
				references.setdefault(url, []).append((doctype, {"doctype": doctype}, fieldname))
			continue
		for row in frappe.db.get_all(
			doctype, fields=["name", fieldname], filters={fieldname: ["like", f"{prefix or ''}%"]}
		):
			if keep(row.get(fieldname)):
				references.setdefault(row[fieldname], []).append(
					(doctype, {"name": row["name"]}, fieldname)
				)

	for _, _, child, child_field in STOREFRONT_CHILD_IMAGE_FIELDS:
		if not frappe.db.exists("DocType", child):
			continue
		for row in frappe.db.get_all(
			child, fields=["name", child_field], filters={child_field: ["like", f"{prefix or ''}%"]}
		):
			if keep(row.get(child_field)):
				references.setdefault(row[child_field], []).append(
					(child, {"name": row["name"]}, child_field)
				)

	return references


def set_image_reference(table: str, selector: dict, fieldname: str, value: str) -> None:
	"""Point one row's image field at `value`."""
	if is_single(table):
		frappe.db.set_single_value(table, fieldname, value, update_modified=False)
		return
	frappe.db.set_value(table, selector, fieldname, value, update_modified=False)


def site_file_path(file_url):
	"""Map a site-relative file url to its path on disk, else None."""
	if file_url.startswith("/files/"):
		return os.path.join(frappe.local.site_path, "public", file_url.lstrip("/"))
	if file_url.startswith("/private/files/"):
		return os.path.join(frappe.local.site_path, file_url.lstrip("/"))
	return None


def extension(file_url: str) -> str:
	return file_url.rsplit(".", 1)[-1].lower() if "." in file_url else ""


def shrink_uploaded_image(doc):
	"""File doc_events hook: downscale, re-encode, and keep the smaller format.

	Runs after File.before_insert - Document.hook composes the class method first
	- so file_url, file_name, is_private and file_type are already set and can be
	corrected here when the format changes.
	"""
	_undo_duplicate_entry(doc)

	path = site_file_path(doc.file_url or "")
	if not path:
		return
	ext = extension(doc.file_url)
	if ext not in RESIZABLE or not os.path.isfile(path):
		return

	# Absolute, because the temp encodes and the final rename have to name the
	# same directory. Frappe's site_path is relative when the bench is driven from
	# the sites directory, and a relative path plus a relative directory resolves
	# against whatever the process cwd happens to be.
	path = os.path.abspath(path)
	target_dir = os.path.dirname(path)

	original_size = os.path.getsize(path)

	try:
		with Image.open(path) as im:
			# An animation is several frames in one file. Re-encoding keeps the
			# first and drops the rest, which is data loss rather than
			# compression. The module docstring has always claimed these are left
			# alone; until now nothing checked.
			if getattr(im, "n_frames", 1) > 1:
				return

			needs_resize = max(im.size) > MAX_DIM
			needs_recompress = ext in {"jpg", "jpeg", "webp"} and original_size > RECOMPRESS_ABOVE
			# A small PNG is not "within bounds" just because it fits: it is 800KB
			# of lossless photograph, and WebP is the entire fix for that.
			needs_format = ext != "webp"
			if not (needs_resize or needs_recompress or needs_format):
				return

			# Phones store rotation in EXIF and re-saving drops it - bake it in first.
			image = ImageOps.exif_transpose(im)
			icc = im.info.get("icc_profile")

			if needs_resize:
				ratio = MAX_DIM / max(image.size)
				image = image.resize(
					(round(image.width * ratio), round(image.height * ratio)), Image.LANCZOS
				)

			image = webp_ready(image)

			webp = _encode(image, "WEBP", target_dir, icc=icc, quality=WEBP_QUALITY, method=6)
			family_fmt = FAMILY[ext]
			family = _encode(image, family_fmt, target_dir, icc=icc)

		fmt, chosen, loser = _choose(webp, family, family_fmt, original_size)
		if chosen is None:
			return

		_apply(doc, path, chosen, fmt, ext)
		_cleanup(loser)
	except Exception:
		frappe.log_error(f"shrink_uploaded_image failed for {doc.file_url}: {frappe.get_traceback()}")


def _undo_duplicate_entry(doc) -> None:
	"""Make a deduplicated upload keep its own bytes instead of a stranger's.

	Frappe deduplicates uploads by content hash, and it does so in
	`File.save_file`, *before* writing anything: if some other File has the same
	`content_hash` and its bytes are still on disk, the new File is pointed at
	that file's url and the upload's own bytes are never written at all. It is
	deliberate, and normally a good idea.

	It is wrong for this shop. Every image here is renamed after it is attached
	- to `{slug}-{n}` when the product is saved - so the File holding a given
	hash gets renamed out from under the index and several rows end up sharing
	one hash. Uploading a photo that happens to match one already in the
	catalogue then silently adopts a stranger's url: the admin uploads their
	second product shot, the upload reports 200, and the storefront serves the
	first product's picture. The new File row also keeps the *uploaded* name,
	type and size while pointing at a file that has none of them, so anything
	trusting those fields is wrong too.

	The flag that disables this, `flags.ignore_duplicate_entry_error`, is read
	inside `File.before_insert`, and `Document.hook` composes the class method
	*before* the doc_event - so there is no hook point early enough to set it.
	The bytes are therefore written here, which is the same effect and needs no
	change to core.

	Detection is exact rather than heuristic: `File.save_file_on_filesystem`
	derives the url from `file_name`, so a url whose basename is not this
	document's own `file_name` can only have come from the dedup branch.
	"""
	if doc.is_remote_file or doc.flags.get("copy_from_existing_file"):
		return
	name = (doc.file_name or "").strip()
	if not name or (doc.file_url or "").rsplit("/", 1)[-1] == name:
		return  # the ordinary path: url and name always agree

	from frappe.core.doctype.file.utils import generate_file_name, get_files_path

	content = doc.get_content()
	if not content:
		return  # attached by url rather than uploaded; nothing of ours to keep

	# The same collision-avoiding name Frappe would have picked had it not
	# deduplicated, so an unrelated file of the same name is never overwritten.
	own_name = generate_file_name(
		name=name, suffix=(doc.content_hash or "")[-6:], is_private=bool(doc.is_private)
	)
	target = get_files_path(own_name, is_private=bool(doc.is_private))
	try:
		with open(target, "wb") as handle:
			handle.write(content)
		os.chmod(target, 0o664)
	except OSError:
		frappe.log_error(
			title="Deduplicated upload could not be written",
			message=f"{name} -> {target}: {frappe.get_traceback()}",
		)
		return

	prefix = "/private/files/" if doc.is_private else "/files/"
	doc.file_name = own_name
	doc.file_url = f"{prefix}{own_name}"
	frappe.logger().info(
		f"shop.files: upload matched an existing file by content hash "
		f"({doc.content_hash[:8]}); wrote its own copy as {doc.file_url}"
	)


def webp_ready(image: Image.Image) -> Image.Image:
	"""Coerce to a mode WebP can store.

	WebP takes RGB, RGBA, greyscale and greyscale+alpha. It cannot take a palette
	image or 16-bit samples, both of which arrive as PNG, and asking it to raises
	mid-encode - after the original has already been dealt with, which is the
	worst place to discover it. RGBA is preserved rather than flattened: PNG is
	the format most likely to be carrying real transparency, and dropping it would
	be silent, permanent data loss.
	"""
	if image.mode in ("RGB", "RGBA", "L", "LA"):
		return image
	if image.mode == "P":
		# An indexed image can carry transparency in its palette, so go via RGBA
		# rather than RGB to keep it.
		return image.convert("RGBA" if "transparency" in image.info else "RGB")
	return image.convert("RGBA" if image.mode.endswith("A") else "RGB")


def _encode(image: Image.Image, fmt: str, directory: str, icc=None, **save_kwargs) -> str | None:
	"""Write `image` as `fmt` into a temp file beside its target. Returns its path.

	The temp file has to be in the destination directory, not the system temp
	dir: the site can sit on a different filesystem (here it does, and /tmp is
	tmpfs), and `os.replace` across two of those is `EXDEV` - "Invalid cross-device
	link". Same directory also keeps the final move atomic, which is what stops a
	half-written file ever being reachable under the name the storefront will
	serve. A prefix on the name makes any stray left by a killed process obvious.
	"""
	fd, tmp = tempfile.mkstemp(prefix=".reloop-", suffix=SUFFIX.get(fmt, ""), dir=directory)
	os.close(fd)
	try:
		payload = image
		if fmt == "JPEG":
			# JPEG has no alpha channel; flattening here is a format limit, not a choice.
			if payload.mode not in ("RGB", "L"):
				payload = payload.convert("RGB")
			save_kwargs.setdefault("quality", QUALITY)
			save_kwargs.setdefault("optimize", True)
			save_kwargs.setdefault("progressive", True)
		elif fmt == "PNG":
			save_kwargs.setdefault("optimize", True)

		if icc:
			save_kwargs["icc_profile"] = icc
		payload.save(tmp, fmt, **save_kwargs)
		return tmp
	except Exception:
		_cleanup(tmp)
		return None


def _choose(webp: str | None, family: str | None, family_fmt: str, original_size: int):
	"""Pick the smaller encode. Returns (format, winner_path, loser_path).

	Returns a None winner when nothing beat the upload, in which case both temp
	files are cleaned up and the original is left exactly as it arrived - a
	re-encode that came out heavier is a regression, not a saving.
	"""
	candidates = [(fmt, path) for fmt, path in (("WEBP", webp), (family_fmt, family)) if path]
	if not candidates:
		return None, None, None

	# Smallest wins. A tie keeps the same-family encode, so a .webp stays .webp.
	ordered = sorted(candidates, key=lambda c: os.path.getsize(c[1]))
	winner_fmt, winner = ordered[0]
	loser = ordered[1][1] if len(ordered) > 1 else None

	if os.path.getsize(winner) >= original_size:
		_cleanup(winner)
		_cleanup(loser)
		return None, None, None

	return winner_fmt, winner, loser


def _apply(doc, path: str, chosen: str, fmt: str, original_ext: str) -> None:
	"""Put the chosen encode in place and correct every field describing it."""
	new_ext = SUFFIX[fmt].lstrip(".")
	final_path = path

	# Read the original's ownership and permissions before it is replaced. The
	# encode is written with mkstemp, which is 0600 owned by whoever ran it - so a
	# migration run as root would leave the storefront's images unreadable to the
	# web server, which is not root. Uploads run as the web user and would land at
	# 0600 too, against this site's 0664 convention.
	original = os.stat(path)

	if new_ext != original_ext:
		# The format changed, so the name has to change with it, or the url will
		# promise a format the bytes are not in.
		from frappe.core.doctype.file.utils import generate_file_name

		name = generate_file_name(
			f"{os.path.splitext(os.path.basename(path))[0]}{SUFFIX[fmt]}",
			is_private=bool(doc.is_private),
		)
		final_path = os.path.join(os.path.dirname(path), name)

	os.replace(chosen, final_path)
	_restore_attributes(final_path, original)

	if final_path != path:
		# The old-format original is now unreferenced by anything.
		_cleanup(path)
		doc.file_url = f"{'/private/files/' if doc.is_private else '/files/'}{os.path.basename(final_path)}"
		doc.file_name = os.path.basename(final_path)
		doc.file_type = CONTENT_TYPE[fmt]

	doc.file_size = os.path.getsize(final_path)
	# File.validate overwrites file_size with the size the client uploaded, which
	# no longer describes the file. recount_file_size puts it right after that.
	doc.flags.reloop_recount_file_size = True


def _restore_attributes(path: str, original: os.stat_result) -> None:
	"""Give the replacement the original file's ownership and permissions.

	Best effort: a process that cannot chown - anything but root, or a shared
	filesystem that refuses it - still gets the mode right, which is the part that
	makes the difference between readable and not.
	"""
	try:
		os.chown(path, original.st_uid, original.st_gid)
	except (OSError, AttributeError):
		pass
	try:
		os.chmod(path, original.st_mode & 0o7777)
	except OSError:
		pass


def recount_file_size(doc):
	"""File doc_events hook on `validate`: correct file_size against the disk.

	`File.validate` ends with `self.file_size = frappe.form_dict.file_size or
	self.file_size`, and a real upload always sends the original size, so it
	overwrites whatever before_insert computed. That was already true for resized
	uploads and is now true for every re-encoded one. Only docs this module
	touched are recomputed.
	"""
	if not doc.flags.get("reloop_recount_file_size"):
		return
	path = site_file_path(doc.file_url or "")
	if path and os.path.isfile(path):
		doc.file_size = os.path.getsize(path)


def _cleanup(path) -> None:
	if path and os.path.exists(path):
		try:
			os.remove(path)
		except OSError:
			pass


# ---------------------------------------------------------------------------
# Product images, named and described, when the product is saved.
#
# Upload-time hygiene above is deliberately format work and nothing else: at
# File.before_insert the file has no product to belong to yet, so naming it
# after one would be a guess. By the time the Shop Product is saved the pairing
# is known, which is where the rest of the job belongs.
# ---------------------------------------------------------------------------

# A Data field with no explicit max_length is 140 in Frappe. Read it rather than
# hardcoding it: an alt_text longer than the limit does not get shortened, it
# raises CharacterLengthExceededError and the product cannot be saved at all.
ALT_FALLBACK_LIMIT = 140


def alt_limit() -> int:
	"""The alt_text field's own character limit."""
	try:
		field = frappe.get_meta("Shop Product Image").get_field("alt_text")
		return int(field.max_length or ALT_FALLBACK_LIMIT) if field else ALT_FALLBACK_LIMIT
	except Exception:
		return ALT_FALLBACK_LIMIT


def already_named(filename: str, slug: str) -> bool:
	"""True when `filename` is this product's own `{slug}-{n}` name.

	Anchored on the real slug rather than a loose digit pattern: a slug can end
	in a digit ("...-solar-red-1"), so "/.+-\\d+/" would also match an unrelated
	upload and skip a rename that still had to happen.

	The optional trailing run is Frappe's own collision hash, and it has to be
	accepted here. When `{slug}-{n}.webp` is already taken on disk,
	`generate_file_name` returns `{slug}-{n}<6 hex chars>.webp` instead of
	overwriting. A strict `{slug}-\\d+\\.ext` test does not match that, so the
	image looked un-renamed on every later save and was renamed again, to a
	fresh hash, on every later save - the url changed each time, which breaks
	caches and leaves the storefront pointing at names the origin no longer
	serves. Matching the hashed form makes the rename idempotent, which is the
	whole point of a name that is supposed to be derived from the product.
	"""
	if not slug or not filename:
		return False
	# `{slug}-{n}` optionally followed by a lowercase 6-character hex run. The
	# hex length is Frappe's `generate_hash(length=6)`; anything longer is not a
	# collision suffix this module produced, so it is left for the rename.
	return bool(re.fullmatch(rf"{re.escape(slug)}-\d+(?:[0-9a-f]{{6}})?\.[A-Za-z0-9]+", filename))


def product_alt_text(doc) -> str:
	"""Alt text for one of this product's images, from the product's own copy.

	An ``alt`` attribute is read aloud by a screen reader and is the text an
	image search matches on, so the product name alone understates both. The
	short description leads, because that is what the admin wrote to describe
	the thing rather than to name it. A hand-written alt_text always wins: this
	only fills a blank.
	"""
	name = (doc.product_name or "").strip()
	body = re.sub(r"\s+", " ", strip_html(doc.short_description or doc.description or "")).strip()
	if body.lower().startswith(name.lower()) and name:
		body = ""
	text = f"{name} - {body}" if name and body else (name or body)

	limit = alt_limit()
	if len(text) <= limit:
		return text
	# Cut on a word so the alt does not end mid-word, and drop the separator the
	# truncation would otherwise leave dangling.
	clipped = text[: limit - 1].rsplit(" ", 1)[0].rstrip(" -,")
	return clipped or text[:limit]


def rename_product_images(doc) -> None:
	"""Shop Product hook: name each image `{slug}-{n}` and fill its alt text.

	Idempotent, because it runs on every save: a name that already matches is
	left alone, so only genuinely new or replaced uploads are moved. Renaming is
	a plain ``os.replace`` of the bytes plus a repoint of the File doc and every
	row referencing it, not a re-encode - the upload hook already produced the
	format, and re-encoding twice would be a second quality loss for nothing.

	A failure on one image is logged and the save continues. A product that
	cannot be renamed is still a product that should sell; an exception here
	would block the admin from saving anything about it at all.
	"""
	slug = (doc.slug or "").strip()
	rows = [row for row in (doc.get("images") or []) if (row.image or "").strip()]
	# Capture what the database says this product points at, before the save
	# overwrites it. `validate` is the last point at which the previous rows are
	# still readable, and prune_product_images - which runs later in this same
	# pass - is the only thing that can tell a dropped photo from one that was
	# never there.
	doc.flags.reloop_previous_images = _saved_image_names(doc.name)

	# Release the photos this save drops *before* naming the ones replacing them.
	# The name a replacement wants is `{slug}-{n}`, and the file occupying that
	# slot is usually the photo being replaced by this very save.
	prune_product_images(doc)

	if not rows:
		return
	if not slug:
		# before_insert assigns the slug from the product name, so on an insert
		# this is only empty if the product has no name either.
		return

	for index, row in enumerate(rows, start=1):
		try:
			_named_image(doc, row, slug, index)
		except Exception:
			frappe.log_error(
				title="Product image rename failed",
				message=f"{doc.name} row {index} ({row.image}): {frappe.get_traceback()}",
			)

		desired = product_alt_text(doc)
		current = (row.alt_text or "").strip()
		# Blank is the obvious case. Alt that is exactly the product name counts
		# too: that is what the importer wrote for every one of the 48 images, so
		# treating it as "already written" would mean the description never
		# reaches the alt attribute at all. Anything else was typed by a person
		# and is left alone.
		if desired and (not current or current == (doc.product_name or "").strip()):
			row.alt_text = desired


# ---------------------------------------------------------------------------
# Reclaiming the files a save drops.
#
# Replacing or removing a photo drops the Shop Product Image row, but nothing
# used to touch the File: the row went, the bytes stayed, and the File doc
# stayed. That orphan is not merely untidy - it permanently occupies the
# `{slug}-{n}` name the *next* photo at that position wants, which is what
# forces Frappe to append a collision hash, which is what made every later save
# rename the image again. So the sweep is not cosmetic: it is what lets the
# naming settle instead of churning.
#
# It has to happen *before* the rename, not after. The name a replacement wants
# is decided in validate, and the file it would collide with is the very one
# being dropped by this same save - so releasing it afterwards leaves the first
# replacement hashed and only ever fixes the second.
# ---------------------------------------------------------------------------


def prune_product_images(doc) -> None:
	"""Shop Product hook: delete image files this product no longer uses.

	Called from `validate`, ahead of the rename, so a freed `{slug}-{n}` slot is
	free by the time the replacement photo asks for it. `validate` is also the
	only point at which the rows being replaced are still readable from the
	database, which is how a dropped photo is told from one that was never there.

	Only files this product claimed are considered, and one is removed only when
	nothing anywhere still references it: a photo shared with another product,
	or sitting in a collection, the shop logo, or a variant's Item row, is left
	alone however few products name it.

	The bytes go after the commit, not during it. The File deletion is part of
	the transaction and rolls back with everything else; unlinking the file
	inside the transaction would leave a committed row pointing at bytes that a
	later exception had already destroyed.
	"""
	slug = (doc.slug or "").strip()
	if not slug:
		return

	current = {os.path.basename(row.image.strip()) for row in (doc.get("images") or []) if row.image}
	previous = set(doc.flags.get("reloop_previous_images") or ())
	if not previous:
		return

	for name in sorted((previous - current) & _names_in_namespace(slug)):
		url = _public_or_private_url(name)
		if not url or _referenced_elsewhere(url, exclude_parent=doc.name):
			continue
		path = site_file_path(url)
		if not path or not os.path.isfile(path):
			continue
		try:
			frappe.delete_doc("File", {"file_url": url}, ignore_permissions=True, force=True)
		except Exception:
			# A File that cannot be deleted is not a reason to block the save;
			# the next save will simply try again.
			frappe.log_error(
				title="Product image prune failed",
				message=f"{doc.name} {url}: {frappe.get_traceback()}",
			)
			continue
		releasing = doc.flags.setdefault("reloop_releasing", {})
		# Absolute, and matching what `_target_name` and `_named_image` key on.
		# `site_file_path` is relative whenever the bench is driven from the
		# sites directory, so a relative key would never match and the queued
		# delete would remove the image the rename had just put there.
		releasing[name] = (os.path.abspath(path), _file_stamp(path))
		frappe.db.after_commit.add(lambda n=name, p=path, d=doc: _finish_release(d, n, p))
		frappe.logger().info(f"shop.files: released dropped product image {url}")


def _file_stamp(path: str) -> tuple | None:
	"""Size and mtime of `path`, as a later delete has to match to proceed."""
	try:
		info = os.stat(path)
	except OSError:
		return None
	return (info.st_size, info.st_mtime_ns)


def _finish_release(doc, name: str, path: str) -> None:
	"""Delete the bytes of a released image, unless the rename reused its path.

	Runs after the commit, because unlinking inside the transaction would
	destroy bytes a later exception could still roll the database back to.

	If the rename claimed this exact name - replacing the photo rather than
	sitting beside it - the file there is now the new image and must be left
	alone. The path is not enough on its own to tell the two apart, so the size
	and mtime recorded at release time are checked as well: only the exact
	bytes that were released are ever unlinked.
	"""
	releasing = doc.flags.get("reloop_releasing") or {}
	entry = releasing.pop(name, None)
	if not entry:
		return
	released_path, stamp = entry
	if _file_stamp(released_path) != stamp:
		return
	_cleanup(path)


def _saved_image_names(product: str) -> set[str]:
	"""The image file names this product's rows hold in the database right now."""
	rows = frappe.db.sql(
		"""select image from `tabShop Product Image`
		where parent=%s and parenttype='Shop Product' and image is not null""",
		(product,),
	)
	return {os.path.basename(r[0].strip()) for r in rows if r[0] and r[0].strip()}


def _names_in_namespace(slug: str) -> set[str]:
	"""Every file name on disk that this product's naming scheme could have produced."""
	pattern = re.compile(rf"{re.escape(slug)}-\d+(?:[0-9a-f]{{6}})?\.[A-Za-z0-9]+$")
	found = set()
	for folder in _file_folders():
		if not os.path.isdir(folder):
			continue
		for entry in os.listdir(folder):
			if pattern.match(entry):
				found.add(entry)
	return found


def _file_folders() -> list[str]:
	"""The two directories a site file can live in, public/files and private/files."""
	site = frappe.local.site_path
	return [
		os.path.abspath(os.path.join(site, "public", "files")),
		os.path.abspath(os.path.join(site, "private", "files")),
	]


def _public_or_private_url(name: str) -> str | None:
	"""The site-relative url for `name`, or None if it is in neither folder."""
	for index, folder in enumerate(_file_folders()):
		if os.path.isfile(os.path.join(folder, name)):
			return f"{'/private/files/' if index else '/files/'}{name}"
	return None


def _referenced_elsewhere(url: str, exclude_parent: str | None = None) -> bool:
	"""True when anything other than `exclude_parent` still points at `url`.

	Checked across every place a storefront image can be held: another product's
	image row, a collection, the shop logo, and an Item's variant photo. A file
	still in use by any of those is not an orphan, however few products name it.
	"""
	if frappe.db.sql(
		"""select name from `tabShop Product Image`
		where image=%s and parenttype='Shop Product' and parent <> %s limit 1""",
		(url, exclude_parent or ""),
	):
		return True
	for doctype, fieldname in STOREFRONT_IMAGE_FIELDS:
		if not frappe.db.exists("DocType", doctype):
			continue
		if is_single(doctype):
			if frappe.db.get_single_value(doctype, fieldname) == url:
				return True
		elif frappe.db.sql(f"select name from `tab{doctype}` where `{fieldname}`=%s limit 1", (url,)):
			return True
	# Item.image is where a variant's own photo is kept (shop.api.variants).
	if frappe.db.exists("DocType", "Item") and frappe.db.sql(
		"select name from `tabItem` where image=%s limit 1", (url,)
	):
		return True
	return False


def _target_name(doc, slug: str, index: int, extension: str, private: bool, directory: str) -> str:
	"""The name this image should take, preferring the clean `{slug}-{n}`.

	`generate_file_name` only hands back the clean name when nothing is on disk
	under it. The photo this save is replacing is deleted after the commit, so
	its bytes are still there while the rename runs and the clean slot looks
	taken - leaving every replacement permanently carrying a collision hash. So
	a slot that this same save is releasing is treated as free, and claiming it
	cancels the pending delete, because the rename has just overwritten it.

	Anything genuinely occupied by someone else's file still gets Frappe's
	collision suffix, which `already_named` recognises so the rename settles.
	"""
	plain = f"{slug}-{index}{extension}"
	releasing = doc.flags.get("reloop_releasing") or {}
	if not os.path.exists(os.path.join(directory, plain)):
		return plain
	if releasing.pop(plain, None):
		# Overwritten by the rename below, so its queued cleanup must not fire.
		return plain
	if os.path.abspath(os.path.join(directory, plain)) in {
		os.path.abspath(entry[0]) for entry in releasing.values() if entry
	}:
		# The occupying file is one this save is releasing. Its bytes are still
		# here until the commit, so claim the name; the queued delete then finds
		# the file changed and leaves the new image alone.
		return plain

	from frappe.core.doctype.file.utils import generate_file_name

	return generate_file_name(plain, is_private=private)


def _named_image(doc, row, slug: str, index: int) -> None:
	"""Move one image to its `{slug}-{n}` name and repoint everything at it."""
	old_url = row.image.strip()
	path = site_file_path(old_url)
	if not path or not os.path.isfile(path):
		return  # external url, or already gone; nothing on disk to rename

	path = os.path.abspath(path)
	current = os.path.basename(path)
	if already_named(current, slug):
		return

	directory = os.path.dirname(path)
	extension_ = os.path.splitext(current)[1].lower() or ".webp"

	private = old_url.startswith("/private/")
	wanted = _target_name(doc, slug, index, extension_, private, directory)
	target = os.path.join(directory, wanted)
	if os.path.abspath(target) == path:
		return

	original = os.stat(path)
	os.replace(path, target)
	_restore_attributes(target, original)

	prefix = "/private/files/" if old_url.startswith("/private/") else "/files/"
	new_url = f"{prefix}{wanted}"
	_repoint(old_url, new_url, wanted, os.path.getsize(target))
	row.image = new_url


def _repoint(old_url: str, new_url: str, new_name: str, size: int) -> None:
	"""Update the File doc and every storefront row that referenced the old url.

	Another product can hold the same image, and the old file is about to stop
	existing under its old name, so every reference moves together. In-memory
	child rows of the document being saved are excluded: their save is coming
	next and would overwrite anything written behind its back.
	"""
	for name in frappe.get_all("File", filters={"file_url": old_url}, pluck="name"):
		try:
			frappe.db.set_value(
				"File",
				name,
				{"file_name": new_name, "file_url": new_url, "file_size": size},
				update_modified=False,
			)
		except Exception:
			pass

	for table, _, child, field in STOREFRONT_CHILD_IMAGE_FIELDS:
		if not frappe.db.exists("DocType", child):
			continue
		frappe.db.set_value(child, {"image": old_url}, field, new_url, update_modified=False)
	for doctype, field in STOREFRONT_IMAGE_FIELDS:
		if frappe.db.exists("DocType", doctype) and not is_single(doctype):
			frappe.db.set_value(doctype, {field: old_url}, field, new_url, update_modified=False)

