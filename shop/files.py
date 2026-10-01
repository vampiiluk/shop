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
import tempfile

import frappe
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
	path = site_file_path(doc.file_url or "")
	if not path:
		return
	ext = extension(doc.file_url)
	if ext not in RESIZABLE or not os.path.isfile(path):
		return

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

			webp = _encode(image, "WEBP", icc=icc, quality=WEBP_QUALITY, method=6)
			family_fmt = FAMILY[ext]
			family = _encode(image, family_fmt, icc=icc)

		fmt, chosen, loser = _choose(webp, family, family_fmt, original_size)
		if chosen is None:
			return

		_apply(doc, path, chosen, fmt, ext)
		_cleanup(loser)
	except Exception:
		frappe.log_error(f"shrink_uploaded_image failed for {doc.file_url}: {frappe.get_traceback()}")


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


def _encode(image: Image.Image, fmt: str, icc=None, **save_kwargs) -> str | None:
	"""Write `image` as `fmt` into a temp file. Returns its path, or None."""
	fd, tmp = tempfile.mkstemp(suffix=SUFFIX.get(fmt, ""))
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
