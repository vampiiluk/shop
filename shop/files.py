"""Image upload hygiene for storefront performance.

Demo images are capped at 800px, but phone uploads arrive at full sensor size
and would undo that work. This shrinks new image uploads in place during
File.before_insert, i.e. before the file is ever served, so URLs, caches and
every upload path (desk forms, front-end uploader, API) stay consistent.

Anything non-image, animated, vector-based, outside the site folders (app
assets, external urls) or already within bounds is left untouched, and any
failure leaves the original file alone - an upload must never break.
"""

import os

import frappe
from PIL import Image, ImageOps

MAX_DIM = 800  # same cap as the re-encoded demo set
QUALITY = 75
RECOMPRESS_ABOVE = 150 * 1024  # heavy-but-small-dimension jpeg/webp still re-encoded
RESIZABLE = {"jpg", "jpeg", "png", "webp"}
RECOMPRESSIBLE = {"jpg", "jpeg", "webp"}


def site_file_path(file_url):
	"""Map a site-relative file url to its path on disk, else None."""
	if file_url.startswith("/files/"):
		return os.path.join(frappe.local.site_path, "public", file_url.lstrip("/"))
	if file_url.startswith("/private/files/"):
		return os.path.join(frappe.local.site_path, file_url.lstrip("/"))
	return None


def shrink_uploaded_image(doc):
	"""File doc_events hook: downscale/re-encode oversized image uploads."""
	path = site_file_path(doc.file_url or "")
	if not path:
		return
	ext = doc.file_url.rsplit(".", 1)[-1].lower() if "." in doc.file_url else ""
	if ext not in RESIZABLE or not os.path.isfile(path):
		return

	try:
		with Image.open(path) as im:
			needs_resize = max(im.size) > MAX_DIM
			needs_recompress = ext in RECOMPRESSIBLE and os.path.getsize(path) > RECOMPRESS_ABOVE
			if not (needs_resize or needs_recompress):
				return

			# phones store rotation in EXIF and re-saving drops it - bake it in first
			image = ImageOps.exif_transpose(im)
			if needs_resize:
				ratio = MAX_DIM / max(image.size)
				image = image.resize(
					(round(image.width * ratio), round(image.height * ratio)), Image.LANCZOS
				)

			kwargs = {"icc_profile": im.info.get("icc_profile")}
			if ext in {"jpg", "jpeg"}:
				if image.mode not in ("RGB", "L"):
					image = image.convert("RGB")
				image.save(
					path, "JPEG", quality=QUALITY, optimize=True, progressive=True, **kwargs
				)
			elif ext == "webp":
				image.save(path, "WEBP", quality=QUALITY, method=6, **kwargs)
			else:
				image.save(path, "PNG", optimize=True)

		doc.file_size = os.path.getsize(path)
	except Exception:
		frappe.log_error(f"shrink_uploaded_image failed for {doc.file_url}: {frappe.get_traceback()}")
