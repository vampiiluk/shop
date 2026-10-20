"""A product's social cards, as a zip.

One call, one file: every card for the product, for both channels, in a
single archive the merchant can hand straight to a post.

The cards are drawn on the way out rather than kept. A set of cards is only
worth making when it is about to be downloaded, and a stored copy would be a
set of files on disk that nothing ever cleans up and that goes stale the
moment the price or the photograph changes.
"""

import frappe

from shop.api import only_managers


@frappe.whitelist(methods=["POST"])
def download(name: str) -> None:
	"""Every social card for a product, both channels, as one zip.

	Returns the archive as a download rather than a path, so the browser gets
	a file it can save without a second request and nothing is left behind
	on the server.
	"""
	only_managers()
	doc = frappe.get_doc("Shop Product", name)

	from shop import social_cards

	data = social_cards.build_zip(doc)
	# The archive is called after the product, so a folder of downloads
	# reads as a list of products rather than a list of urls.
	filename = social_cards.safe_filename(doc.product_name or doc.name)

	frappe.local.response.filename = f"{filename}.zip"
	frappe.local.response.filecontent = data
	frappe.local.response.type = "download"


@frappe.whitelist()
def describe(name: str) -> dict:
	"""What a download will contain, without drawing any of it.

	The button says how many cards there are and how big they are, so the
	merchant knows what they are about to get before they wait for it.
	"""
	only_managers()
	doc = frappe.get_doc("Shop Product", name)
	from shop import social_cards

	images = len(doc.images or [])
	channels = {
		key: {"label": value["label"], "width": value["size"][0], "height": value["size"][1]}
		for key, value in social_cards.CHANNELS.items()
	}
	# Instagram takes one card whatever the product has; TikTok takes one
	# per photograph.
	cards = 1 + images
	return {
		"images": images,
		"cards": cards,
		"channels": channels,
	}
