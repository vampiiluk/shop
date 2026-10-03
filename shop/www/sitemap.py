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
		links.setdefault(loc, _lastmod(lastmod))

	for route, page in get_pages().items():
		if page.sitemap:
			add(get_url(route), nowdate())

	for route, data in get_public_pages_from_doctypes().items():
		if route:
			add(get_url(route), data["modified"])

	for route, modified in _shop_routes():
		add(get_url(route), modified)

	add(get_url("") or "/", _home_modified())

	return {"links": [{"loc": loc, "lastmod": lastmod} for loc, lastmod in links.items()]}


def _home_modified():
	"""When the home page last changed.

	The home page is the one URL that cannot be discovered by either of the
	sweeps above, which is why it was missing: Builder stores its route as
	``home`` but serves the page at ``/``, so ``get_url("home")`` is a URL that
	does not resolve, and robots.txt disallows ``/home`` anyway so it must never
	be advertised. It has to be added by hand, at the URL it is actually served
	on.

	``lastmod`` comes from the Builder page when it can be read, because a
	home page that has not changed should not tell a crawler to come back for
	news. Anything unreadable falls back to today, which is the same rule
	``_lastmod`` applies to an unparseable value.
	"""
	try:
		row = frappe.get_all(
			"Builder Page", filters={"route": "home"}, fields=["modified"], limit=1
		)
		if row and row[0].get("modified"):
			return row[0]["modified"]
	except Exception as exc:
		frappe.log_error(f"shop sitemap: home page unreadable: {exc}", "Shop Sitemap")
		frappe.clear_messages()
	return nowdate()


def _lastmod(value) -> str:
	"""A ``lastmod`` in one of the two forms W3C datetime actually accepts.

	Search Console rejected 15 of the 17 entries as "Invalid date". The values were
	Python datetimes rendered straight into the XML: ``2026-10-01 21:49:35.032357``.
	A space where the spec wants ``T``, and microseconds on the end -- so it is
	neither of the two legal shapes, ``YYYY-MM-DD`` or
	``YYYY-MM-DDThh:mm:ss+00:00``. Only the static-page branch was clean, which is
	why exactly the two entries that were already correct were the two that had
	never been through a datetime.

	Dates are what search engines act on here, and a day is the precision a sitemap
	needs; the time only adds bytes and a second way to be invalid. Anything
	unparseable falls back to today rather than emitting a broken value, since a
	wrong-but-valid date is more dangerous than an absent one.
	"""
	import datetime as dt

	if isinstance(value, (dt.datetime, dt.date)):
		return value.strftime("%Y-%m-%d")

	text = str(value or "").strip()
	# Shape is not validity: "2026-13-45" is the right shape and not a real date,
	# so the tail is parsed rather than sliced. strptime raises, and an
	# out-of-range date would otherwise go to Google to be rejected again.
	for candidate in (text, text[:10]):
		try:
			return dt.datetime.strptime(candidate, "%Y-%m-%d").strftime("%Y-%m-%d")
		except ValueError:
			continue
	return dt.date.today().strftime("%Y-%m-%d")


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
