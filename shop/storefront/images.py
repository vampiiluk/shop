"""Which of a product's images can actually be served.

A Shop Product Image row is only a url. Nothing checks that the file behind it
is still there, so an image that was renamed or removed on disk keeps rendering
as a broken picture on the product page and in the catalog grid.

Renaming is the usual cause. ``shop.files.rename_product_images`` moves the file
to ``{slug}-{n}.webp`` on save, and Frappe appends a hash when that name is
already taken. A row left pointing at the name the file had before stays a valid
url that no longer resolves - the storefront cannot tell the difference, so it
renders it and the customer sees a broken image.

These checks are on the request path, so they are one stat per image and no
database work. A row that cannot be served is left in the database: the file may
be re-uploaded, and quietly deleting the merchant's image list would lose the
alt text and the ordering.
"""

import os

import frappe

from shop.files import site_file_path


def servable(file_url: str | None) -> str | None:
	"""``file_url`` if it can be served, else None.

	Anything that is not a site file - an external url - is passed through: this
	module is only here to catch rows pointing at files that have gone.
	"""
	url = (file_url or "").strip()
	if not url:
		return None
	path = site_file_path(url)
	if not path:
		return url
	return url if os.path.isfile(path) else None


def product_images(doc) -> list[dict]:
	"""A product's images as the storefront should render them."""
	kept, missing = [], []
	for row in doc.images or []:
		url = servable(row.image)
		if url:
			kept.append({"image": url, "alt_text": row.alt_text})
		else:
			missing.append(row.image)
	if missing:
		frappe.log_error(
			title="Product image missing on disk",
			message=(
				f"{doc.name} ({doc.product_name}) lists {len(missing)} image(s) whose file is "
				f"not on disk, so they were left out of the page:\n" + "\n".join(missing)
			),
		)
	return kept


def first_images(product_names: list[str]) -> dict[str, str]:
	"""The card image per product: the first one that can actually be served."""
	if not product_names:
		return {}
	rows = frappe.get_all(
		"Shop Product Image",
		filters={"parent": ["in", product_names]},
		fields=["parent", "image"],
		order_by="parent, idx",
	)
	images: dict[str, str] = {}
	for row in rows:
		# setdefault, so a missing first image falls through to the next one
		# rather than leaving the card blank.
		if row.parent in images:
			continue
		url = servable(row.image)
		if url:
			images[row.parent] = url
	return images
