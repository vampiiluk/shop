"""Sitemap for the storefront, which also lists product and collection pages.

Frappe's own sitemap lists two things: Web Pages with the ``sitemap`` flag, and
doctypes that have a web view, a published flag and a ``route`` column. ``Shop
Product`` has none of the third -- it has no ``route`` column at all, because the
storefront builds ``/product/<slug>`` in code (``catalog.decorate``) -- and it is
not marked as a web view. So no product page was ever in the sitemap. They were
reachable only by following links out of ``/products``: fine for a crawler that
already knows the site, useless for one that does not, which is the whole point of
a sitemap.

This page also de-duplicates. Frappe lists a route once from the Web Page table and
again from the doctype sweep, so ``/about`` and ``/contact`` each appeared twice in a
six-URL sitemap.

It defers to Frappe's two sources rather than replacing them, so a new Builder page
or a newly web-viewable doctype is picked up here too without touching this file.
"""

import frappe
from frappe.utils import get_url, nowdate
from frappe.website.router import get_pages

# Imported, not reimplemented: this file shadows frappe/www/sitemap.py for the
# /sitemap.xml route, and shadowing it must not mean losing behaviour.
from frappe.www.sitemap import get_public_pages_from_doctypes

base_template_path = "www/sitemap.xml"

# Frappe's own is 1. The sitemap is what a crawler reads while deciding how often to
# come back, so regenerating it per hit would be work spent on an identical answer.
no_cache = 1


def get_context(context):
	links = {}

	def add(loc, lastmod):
		links.setdefault(loc, lastmod)

	for route, page in get_pages().items():
		if page.sitemap:
			add(get_url(route), nowdate())

	for route, data in get_public_pages_from_doctypes().items():
		if route:
			add(get_url(route), data["modified"])

	for route, modified in _shop_routes():
		add(get_url(route), modified)

	return {"links": [{"loc": loc, "lastmod": lastmod} for loc, lastmod in links.items()]}


def _shop_routes():
	"""Published product and collection routes, paired with their modified date.

	Only published rows. An unpublished product 404s for a crawler, and a sitemap is
	an explicit list of things worth fetching -- listing dead URLs spends a crawl
	budget on nothing.

	Robots exclusions are honoured for the same reason Frappe applies them to its
	own entries: ``/cart`` and friends are per-visitor and nothing there is worth
	an index.
	"""
	if not _has("Shop Product"):
		return

	blocked = _blocked_prefixes()

	def allowed(route):
		return not any(route == p or route.startswith(p.rstrip("/") + "/") for p in blocked)

	out = []
	for doctype, prefix, condition in (
		("Shop Product", "/product", "published"),
		("Shop Collection", "/collection", "published"),
	):
		if not _has(doctype):
			continue
		try:
			rows = frappe.get_all(
				doctype,
				filters={condition: 1, "slug": ("is", "set")},
				fields=["slug", "modified"],
				order_by="slug asc",
			)
		except Exception as exc:  # a missing column must not take the sitemap down
			frappe.log_error(f"shop sitemap: {doctype} unreadable", "Shop Sitemap")
			frappe.clear_messages()
			print(f"shop sitemap: skipping {doctype}: {exc}")
			continue
		for row in rows:
			route = f"{prefix}/{row.slug}"
			if allowed(route):
				out.append((route, row.modified))

	return out


def _has(doctype):
	return bool(frappe.db.exists("DocType", doctype))


def _blocked_prefixes():
	"""Paths robots.txt disallows, so the sitemap does not contradict it."""
	from urllib import robotparser

	robots = frappe.get_single_value("Website Settings", "robots_txt")
	if not robots:
		return []
	parser = robotparser.RobotFileParser()
	parser.parse(robots.splitlines())
	out = []
	for line in robots.splitlines():
		line = line.strip()
		if line.lower().startswith("disallow:"):
			path = line.split(":", 1)[1].strip()
			if path:
				out.append(path)
	return out
