"""Product images as an absolute URL a remote catalogue can actually fetch.

Both Meta Commerce and Google Merchant read ``image_link`` from their own
servers, not through the shop. A stored ``/files/...`` path is therefore not
enough: it has to be absolute, percent-encoded (23 of this shop's images have a
space in the filename), and in a format the catalogue accepts. Google's product
data specification has no WebP, and Meta's fetcher drops it, while 45 of the
shop's 48 original product images were WebP -- so without a conversion the
catalogue had no imagery at all.

The derivative is cached as a public File with a deterministic name derived from
the source, so a second feed sync reuses it instead of converting again. The
``meta-`` prefix is historical, from when this module lived in the Meta
integration; keeping it means the images already converted are reused.
"""

import hashlib
import os
import urllib.parse

import frappe

from shop.storefront.urls import SITE_BASE

# JPEG and PNG are accepted by both catalogues. Other raster formats are
# converted rather than sent and refused.
FEED_IMAGE_FORMATS = (".jpg", ".jpeg", ".png")
# Longest edge. Large enough for Google's 500px minimum with room to zoom,
# small enough that a phone on mobile data opens the card quickly.
FEED_IMAGE_EDGE = 1200
JPEG_QUALITY = 85


def absolute_url(url: str) -> str:
	"""Absolute URL for a stored (usually root-relative) asset path.

	The path is percent-encoded. A raw space is not a valid URL character:
	remote fetchers reject it outright, so those products silently had no image.
	"""
	if not url:
		return ""
	if url.startswith(("http://", "https://")):
		return url
	parts = urllib.parse.urlsplit(SITE_BASE + ("" if url.startswith("/") else "/") + url)
	return urllib.parse.urlunsplit(
		(parts.scheme, parts.netloc, urllib.parse.quote(parts.path), parts.query, parts.fragment)
	)


def _is_feed_format(path: str) -> bool:
	return path.lower().split("?")[0].endswith(FEED_IMAGE_FORMATS)


def _jpeg_for(path: str) -> str:
	"""A JPEG copy of a non-JPEG image, cached as a public File.

	Returns the original path unchanged if conversion is not possible. Sending a
	format a catalogue may refuse is no worse than sending nothing, and the
	caller already tolerates a product with no usable image.
	"""
	if _is_feed_format(path):
		return path
	relative = path.lstrip("/")
	# Absolute, for the same reason files.py is: site_path is relative when the
	# bench is driven from the sites directory, and a relative path resolved
	# against whatever cwd the sync happens to have will silently write the
	# derivative somewhere that is never served.
	source = os.path.abspath(os.path.join(frappe.get_site_path(), "public", relative))
	if not os.path.isfile(source):
		return path

	stem = os.path.splitext(os.path.basename(relative))[0]
	ext_or_hash = hashlib.sha1(f"{relative}:{_file_signature(source)}".encode()).hexdigest()[:10]
	name = f"meta-{stem}-{ext_or_hash}.jpg"
	target = os.path.join(frappe.get_site_path(), "public", "files", name)
	target = os.path.abspath(target)
	if not os.path.isfile(target):
		try:
			_convert_to_jpeg(source, target)
		except Exception as exc:
			frappe.log_error(
				title="Feed image conversion failed",
				message=f"{relative} -> files/{name}: {exc}",
			)
			return path
	return "/files/" + name


def _file_signature(path: str) -> str:
	"""Size and mtime, so an edited image does not reuse an old derivative."""
	stat = os.stat(path)
	return f"{stat.st_size}-{int(stat.st_mtime)}"


def _convert_to_jpeg(source: str, target: str) -> None:
	"""Re-encode as JPEG, flattening onto white.

	WebP and PNG can carry an alpha channel and JPEG cannot, so without a
	flatten the transparent areas of a product shot come out black. Product
	photography on this shop is shot against white, so white is the right matte.
	"""
	from PIL import Image

	with Image.open(source) as img:
		img.load()
		if img.mode in ("RGBA", "LA", "P"):
			img = img.convert("RGBA")
			matte = Image.new("RGB", img.size, (255, 255, 255))
			matte.paste(img, mask=img.split()[-1])
			img = matte
		else:
			img = img.convert("RGB")
		img.thumbnail((FEED_IMAGE_EDGE, FEED_IMAGE_EDGE), Image.LANCZOS)
		os.makedirs(os.path.dirname(target), exist_ok=True)
		img.save(target, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)


def image_link(image: str) -> str:
	"""The one image for a product, as an absolute URL a feed can fetch."""
	if not image:
		return ""
	return absolute_url(_jpeg_for(image))
