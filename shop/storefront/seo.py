"""Structured data and page metadata for the storefront.

Every Builder page on the shop runs a page-data script that calls into
``shop.storefront.page_data``. Builder merges that result straight into the page
context, and where the returned dict carries ``metatags`` those tags replace the
defaults Builder derives from ``page_title``. Because ``page_title`` was filled
in from the route slug when the theme was generated, every page rendered as
``Home`` / ``Products`` / ``Product`` — the same string for every product on the
site — and no page carried a description, a canonical or any structured data.

``seo_for()`` returns the two keys the renderer reads:

``metatags``
    Title, description, canonical and the Open Graph set, built from the shop's
    own settings and the product on the page.

``_head_html``
    A ``application/ld+json`` block, which the page template renders raw into
    ``<head>``.

Both are generated rather than written by hand, so they stay true when a price,
a product name or a policy changes. A tag set by hand on the Builder page wins:
``metatags`` here is merged under Builder's own values for the reason above, and
this never fights a human for control of the head.
"""

from __future__ import annotations

import json
import re

import frappe
from frappe.utils import fmt_money

# Google truncates a title past roughly 60 characters and a description past
# about 160. These are budgets to stay inside, not targets to fill.
TITLE_BUDGET = 60
DESCRIPTION_BUDGET = 158

FALLBACK_STORE_NAME = "reloop"

# How many products an OfferCatalog describes. The whole published range, so an
# answer engine can read what is for sale from one request; capped so a large
# catalogue cannot make the JSON-LD bigger than the page it describes.
CATALOG_LIMIT = 120

# The catalogue barely changes between page loads, so it is fetched once and held
# briefly. It is invalidated alongside the hero's shelf list.
CATALOG_CACHE_KEY = "shop:seo_catalog"
CATALOG_TTL = 600


def site_url(path: str = "/") -> str:
	"""An absolute URL on this site, built from the configured host.

	The root has no trailing slash, which is the form Frappe's own
	``get_url()`` produces and therefore the form Builder's canonical is already
	in. Returning a slash here would leave a page advertising two canonical
	spellings of its own home page.
	"""
	if not path.startswith("/"):
		path = f"/{path}"
	path = path.rstrip("/")
	return frappe.utils.get_url(path)


def store_settings() -> dict:
	"""The shop's own settings, with defaults for anything unset.

	Only the fields this doctype actually has are read. It carries no tagline or
	contact fields of its own, so those come from the page copy the theme already
	renders rather than being invented here.
	"""
	settings = {}
	for field in ("store_name", "currency", "whatsapp_number", "address_country"):
		try:
			settings[field] = frappe.db.get_single_value("Shop Settings", field)
		except Exception:
			settings[field] = None
	settings["shop_name"] = settings.get("store_name") or FALLBACK_STORE_NAME
	settings["currency"] = settings.get("currency") or "PKR"
	return settings


def requested_route() -> str:
	"""The route being served, without its leading slash.

	Read from the path rather than passed in, so an endpoint shared by several
	static pages can still describe the one actually being asked for. The page
	renderer resolves a dynamic segment (product/<slug>) to the concrete path
	before the page-data script runs, so a real slug is available here too.
	"""
	path = (frappe.local.request.path if frappe.local.request else "") or "/"
	# Drop a trailing file extension: "/faq.html" is still the FAQ page.
	path = path.split("?", 1)[0].split("#", 1)[0]
	if "." in path.rsplit("/", 1)[-1]:
		path = path.rsplit(".", 1)[0]
	return path.strip("/")


def condense(text: str, budget: int) -> str:
	"""Trim to a budget on a word boundary, so nothing is cut mid-word."""
	text = " ".join((text or "").split())
	if len(text) <= budget:
		return text
	cut = text[:budget].rsplit(" ", 1)[0].rstrip(" ,.;:-—")
	return f"{cut}…" if cut else text[:budget]


def _money(value, currency: str) -> str | None:
	if value in (None, ""):
		return None
	try:
		return fmt_money(float(value), precision=2, currency=currency)
	except (TypeError, ValueError):
		return None


def _plain(html: str) -> str:
	return " ".join(re.sub(r"<[^>]+>", " ", html or "").split())


# --- descriptions -----------------------------------------------------------


def _product_description(product: dict, settings: dict) -> str:
	parts = [_plain(product.get("short_description") or product.get("product_name") or "")]
	condition = (product.get("condition") or "").strip()
	if condition and condition.lower() not in ("", "new", "preloved"):
		parts.append(f"Condition: {condition}.")
	price = _money(product.get("price"), settings["currency"])
	if price:
		parts.append(f"{price}.")
	return " ".join(p for p in parts if p)


def _description(route: str, settings: dict, product: dict | None) -> str:
	store = settings["shop_name"]
	if product:
		return _product_description(product, settings)
	if route in ("home", "/", ""):
		return (
			f"{store} sells everyday essentials, from brand-new finds to gently preloved favourites. "
			"A short catalogue of useful things, honestly priced."
		)
	if route.startswith("product/"):
		return f"Everyday essentials from {store}, new and gently preloved."
	if route.startswith("products") or route.startswith("collection"):
		return (
			f"Browse everything {store} sells — new and gently preloved everyday essentials. "
			"Filter by size, colour and price, with cash on delivery."
		)
	if route.startswith("faq"):
		return "Delivery, returns, sizing and payment questions answered in full."
	if route.startswith("about"):
		return f"Why {store} exists: a short catalogue of useful everyday things, honestly priced."
	if route.startswith("contact"):
		return f"Reach {store} by email, phone or WhatsApp."
	# Shop Settings carries no tagline field, so an unrecognised route falls back
	# to the store name rather than to an empty description.
	return f"{store} — everyday essentials, new and preloved."


def _title(route: str, settings: dict, product: dict | None) -> str:
	store = settings["shop_name"]
	if product:
		name = product.get("product_name") or product.get("name") or ""
		return condense(f"{name} — {store}", TITLE_BUDGET)
	labels = {
		"home": f"{store} — everyday essentials, new and preloved",
		"products": f"All products — {store}",
		"faq": f"FAQ — {store}",
		"about": f"About — {store}",
		"contact": f"Contact — {store}",
		"cart": f"Your cart — {store}",
		"checkout": f"Checkout — {store}",
	}
	label = labels.get(route, "")
	if not label and route.startswith("collection"):
		label = f"Shop — {store}"
	return condense(label or store, TITLE_BUDGET)


# --- structured data --------------------------------------------------------


def _organization(settings: dict) -> dict:
	node = {
		"@type": "Organization",
		"@id": f"{site_url('/')}#organization",
		"name": settings["shop_name"],
		"url": site_url("/"),
	}
	contact = {}
	if settings.get("whatsapp_number"):
		contact["telephone"] = settings["whatsapp_number"]
	if contact:
		node["contactPoint"] = {
			"@type": "ContactPoint",
			"contactType": "customer service",
			"availableLanguage": ["en", "ur"],
			**contact,
		}
	if settings.get("address_country"):
		node["address"] = {"@type": "PostalAddress", "addressCountry": settings["address_country"]}
	return node


def _website(settings: dict) -> dict:
	return {
		"@type": "WebSite",
		"@id": f"{site_url('/')}#website",
		"url": site_url("/"),
		"name": settings["shop_name"],
		"inLanguage": "en",
		"publisher": {"@id": f"{site_url('/')}#organization"},
	}


def _breadcrumbs(route: str, title: str) -> dict | None:
	segments = [s for s in (route or "").split("/") if s and not s.startswith(":")]
	if len(segments) < 2:
		return None
	items = []
	path = ""
	for index, segment in enumerate(segments):
		path = f"{path}/{segment}"
		last = index == len(segments) - 1
		items.append(
			{
				"@type": "ListItem",
				"position": index + 1,
				"name": title if last else segment.replace("-", " ").title(),
				"item": site_url(path),
			}
		)
	return {"@type": "BreadcrumbList", "itemListElement": items}


def _image_urls(product: dict) -> list[str]:
	"""Every image on a product, absolute.

	``product_page`` passes ``images`` as a list of rows (each a dict with an
	``image``); a listing passes a single flat ``image``. Both are accepted so a
	caller does not have to reshape the data to get a picture into the graph.
	"""
	urls: list[str] = []
	images = product.get("images") or []
	for entry in images:
		raw = entry.get("image") if isinstance(entry, dict) else entry
		if raw:
			urls.append(site_url(raw))
	if not urls and product.get("image"):
		urls.append(site_url(product["image"]))
	return urls


def _product_node(product: dict, settings: dict) -> dict:
	node = {
		"@type": "Product",
		"@id": f"{site_url(product.get('route') or '/')}#product",
		"name": product.get("product_name") or product.get("name"),
		"url": site_url(product.get("route") or "/"),
		"description": condense(_plain(product.get("short_description") or ""), DESCRIPTION_BUDGET),
	}
	if product.get("item"):
		node["sku"] = product["item"]
	condition = (product.get("condition") or "").strip()
	if condition and condition.lower() not in ("", "new", "preloved"):
		node["itemCondition"] = "https://schema.org/UsedCondition"
		node["brand"] = {"@type": "Brand", "name": condition}
	images = _image_urls(product)
	if images:
		node["image"] = images
	if product.get("price") not in (None, ""):
		offer = {
			"@type": "Offer",
			"url": site_url(product.get("route") or "/"),
			"priceCurrency": settings["currency"],
			"price": f"{float(product['price']):.2f}",
			"availability": (
				"https://schema.org/InStock"
				if product.get("in_stock")
				else "https://schema.org/OutOfStock"
			),
		}
		compare_at = product.get("compare_at_price")
		if compare_at and float(compare_at) > float(product["price"]):
			offer["priceSpecification"] = {
				"@type": "UnitPriceSpecification",
				"priceCurrency": settings["currency"],
				"price": f"{float(compare_at):.2f}",
			}
		node["offers"] = offer
	return node


def _offer_catalog(settings: dict, products: list[dict] | None) -> dict | None:
	"""The whole published range, so one request describes what is for sale.

	Built from the products the page already fetched rather than from a second
	query: price, stock and the image are computed per render, not stored, so a
	query of the doc alone cannot produce them. Reusing ``get_products`` output
	also means the structured data cannot drift from what the page shows.
	"""
	if not products:
		return None
	items = []
	for index, row in enumerate(products, start=1):
		route = row.get("route") or f"/product/{row.get('slug') or row.get('name')}"
		offer = {"@type": "Offer", "url": site_url(route), "priceCurrency": settings["currency"]}
		if row.get("price") not in (None, ""):
			offer["price"] = f"{float(row['price']):.2f}"
			offer["availability"] = (
				"https://schema.org/InStock" if row.get("in_stock") else "https://schema.org/OutOfStock"
			)
		product = {
			"@type": "Product",
			"name": row.get("product_name") or row.get("name"),
			"url": site_url(route),
		}
		if row.get("image"):
			product["image"] = site_url(row["image"])
		condition = (row.get("condition") or "").strip()
		if condition and condition.lower() not in ("", "new", "preloved"):
			product["itemCondition"] = "https://schema.org/UsedCondition"
		items.append({"@type": "Offer", "position": index, "itemOffered": product, "offer": offer})
	return {
		"@type": "OfferCatalog",
		"@id": f"{site_url('/')}#catalog",
		"name": f"{settings['shop_name']} catalogue",
		"url": site_url("/products"),
		"numberOfItems": len(products),
		"itemListElement": items,
	}


def _cached_offer_catalog(settings: dict) -> dict | None:
	"""The OfferCatalog node, fetched once and held for a few minutes.

	The catalogue is the same on every listing page and changes only when the
	shop does, so asking for the whole range on every page load would be work
	spent to produce an identical answer. The currency is stamped back on from
	Shop Settings after the read rather than baked into the cached value, so a
	currency change takes effect at once instead of waiting out the TTL.
	"""
	from shop.storefront import catalog

	payload = frappe.cache().get_value(CATALOG_CACHE_KEY)
	if payload is None:
		products = catalog.get_products(limit=CATALOG_LIMIT)["products"]
		node = _offer_catalog(settings, products)
		if node is None:
			return None
		for item in node["itemListElement"]:
			item.get("offer", {}).pop("priceCurrency", None)
		payload = json.dumps(node, ensure_ascii=False, separators=(",", ":"))
		frappe.cache().set_value(CATALOG_CACHE_KEY, payload, expires_in_sec=CATALOG_TTL)

	node = json.loads(payload)
	for item in node.get("itemListElement", []):
		item.setdefault("offer", {})["priceCurrency"] = settings["currency"]
	return node


def _faq_node() -> dict | None:
	"""The FAQ answers, if they are kept as rows rather than as page blocks."""
	if not frappe.db.table_exists("Shop FAQ"):
		return None
	rows = frappe.get_all(
		"Shop FAQ",
		filters={"published": 1},
		fields=["question", "answer"],
		order_by="idx asc",
		limit_page_length=50,
	)
	entities = [
		{
			"@type": "Question",
			"name": row["question"],
			"acceptedAnswer": {"@type": "Answer", "text": _plain(row["answer"])},
		}
		for row in rows
		if row.get("question") and row.get("answer")
	]
	if not entities:
		return None
	return {"@type": "FAQPage", "mainEntity": entities}


def _graph(route: str, settings: dict, product: dict | None) -> dict:
	graph = [_organization(settings), _website(settings)]

	crumbs = _breadcrumbs(route, _title(route, settings, product))
	if crumbs:
		graph.append(crumbs)

	if product:
		graph.append(_product_node(product, settings))
	elif route.startswith("products") or route in ("home", "/", ""):
		node = _cached_offer_catalog(settings)
		if node:
			graph.append(node)

	if route.startswith("faq"):
		faq = _faq_node()
		if faq:
			graph.append(faq)

	return {"@context": "https://schema.org", "@graph": graph}


# --- public entry point -----------------------------------------------------


def seo_for(route: str = "", product: dict | None = None) -> dict:
	"""The ``metatags`` and ``_head_html`` a Builder page should render.

	``route`` is the page's route without its leading slash (``home``,
	``products``, ``product/zip-hoodie``). ``product`` is the product the page is
	about, if any.
	"""
	route = (route or "").strip("/")
	settings = store_settings()
	# product_page() passes a detail dict that carries no `route`, and a listing
	# passes one that does. Filling it in from the page's own route means an
	# Offer can never point at the site root because a key was missing.
	if product is not None and not product.get("route"):
		product = {**product, "route": f"/{route}"}
	title = _title(route, settings, product)
	description = condense(_description(route, settings, product), DESCRIPTION_BUDGET)
	# "home" is the Builder route name; the page itself is served at the root,
	# so its canonical has to be "/" or a crawler is pointed at a URL that does
	# not exist.
	canonical = site_url("/" if route in ("", "home") else f"/{route}")
	image = site_url((product or {}).get("image") or "/assets/shop/images/og-default.webp")

	metatags = {
		"title": title,
		"description": description,
		"og:title": title,
		"og:description": description,
		"og:type": "product" if product else "website",
		"og:url": canonical,
		"og:site_name": settings["shop_name"],
		"og:image": image,
		"twitter:card": "summary_large_image",
		"twitter:title": title,
		"twitter:description": description,
		"twitter:image": image,
	}

	graph = json.dumps(
		_graph(route, settings, product), ensure_ascii=False, separators=(",", ":")
	)
	return {
		# `title` is what the page template puts between <title> tags; Builder
		# defaults it to the route slug and merges this over the top, so without
		# this key every page is titled "Home" or "Product".
		"title": title,
		# Builder emits the canonical itself from this key. Handing it back here
		# rather than writing a <link> into _head_html keeps one canonical on the
		# page instead of two that disagree about the trailing slash.
		"canonical_url": canonical,
		"metatags": metatags,
		"_head_html": '<script type="application/ld+json">{}</script>'.format(
			graph.replace("</", "<\\/")
		),
	}
