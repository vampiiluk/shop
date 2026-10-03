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
from urllib.parse import quote, urlparse

import frappe
from frappe.utils import fmt_money

# Google truncates a title past roughly 60 characters and a description past
# about 160. These are budgets to stay inside, not targets to fill.
TITLE_BUDGET = 60
DESCRIPTION_BUDGET = 158

# The share card served from the app's own public/ directory. A stable path, not a
# File doctype record: crawlers cache these URLs hard, and a path that moves when
# a File is renamed leaves every share that already resolved it pointing at
# nothing.
OG_DEFAULT_IMAGE = "/assets/shop/img/og-card.png"
OG_CARD_WIDTH = 1200
OG_CARD_HEIGHT = 630

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

	The path is percent-encoded. ``get_url()`` concatenates and encodes nothing,
	and the file paths it is handed carry raw spaces -- an uploaded photo lands as
	``/files/Image generation_10_01_1052_01.webp``. That is not a URL, and a URL-typed
	schema.org property has to be one: Google is given an ``image`` it cannot
	resolve. The sitemap already encodes these same paths, so the two were
	disagreeing about the address of the same file.

	``%`` is left alone so an already-encoded path is not encoded a second time
	into ``%2520``.
	"""
	if not path.startswith("/"):
		path = f"/{path}"
	path = path.rstrip("/")
	return frappe.utils.get_url(quote(path, safe="/%"))


def store_settings() -> dict:
	"""The shop's own settings, with defaults for anything unset.

	Only the fields this doctype actually has are read. It carries no tagline or
	contact fields of its own, so those come from the page copy the theme already
	renders rather than being invented here.
	"""
	settings = {}
	# address_locality / address_postal / return_window_days are newer than some
	# installs' Shop Settings. get_single_value raises on a column that is not
	# there, so each is read independently and simply reads as absent rather than
	# taking the whole structured-data block down with it.
	for field in (
		"store_name",
		"currency",
		"whatsapp_number",
		"address_country",
		"address_locality",
		"address_postal",
		"return_window_days",
		"flat_shipping_rate",
		"free_shipping_above",
	):
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
		contact["telephone"] = _e164(settings["whatsapp_number"])
	if contact:
		node["contactPoint"] = {
			"@type": "ContactPoint",
			"contactType": "customer service",
			"availableLanguage": ["en", "ur"],
			**contact,
		}
	address = {}
	if country := _country_code(settings.get("address_country")):
		address["addressCountry"] = country
	# The rest of a PostalAddress is per Google's own report optional, and each part
	# is only emitted once it is actually configured. A guessed street address would
	# be a false claim about where a business is, printed in search results.
	if locality := (settings.get("address_locality") or "").strip():
		address["addressLocality"] = locality
	if postal := (settings.get("address_postal") or "").strip():
		address["postalCode"] = postal
	if address:
		node["address"] = {"@type": "PostalAddress", **address}
	return node


# Addressed the way a human types it, which is how Default Country is filled in.
# Small on purpose: only the countries this shop could plausibly be, plus a
# pass-through for anything already a code. A full table would be a country list
# masquerading as a lookup, and the setting is editable by hand anyway.
_COUNTRY_CODES = {
	"pakistan": "PK",
	"india": "IN",
	"united kingdom": "GB",
	"uk": "GB",
	"united states": "US",
	"usa": "US",
	"united arab emirates": "AE",
	"uae": "AE",
	"canada": "CA",
	"australia": "AU",
	"turkey": "TR",
	"turkiye": "TR",
	"saudi arabia": "SA",
}


def _country_code(value: str | None) -> str | None:
	"""schema.org wants an ISO 3166-1 alpha-2 code, not a country name.

	The setting holds "Pakistan", which is not a code. Google then cannot build the
	Country node and reports it as invalid, then reports that node as having no name
	-- one wrong value, two warnings. Anything already two letters is passed through
	unchanged so an existing correct setting is not mangled.
	"""
	raw = (value or "").strip()
	if not raw:
		return None
	if len(raw) == 2 and raw.isalpha():
		return raw.upper()
	return _COUNTRY_CODES.get(raw.lower())


def _e164(value: str) -> str:
	"""telephone wants E.164, which is a leading + and no separators.

	The setting is stored as digits only because that is what wa.me links need, so
	the plus has to be added here rather than in the data: changing the stored value
	would change every WhatsApp link built from it.
	"""
	digits = re.sub(r"\D", "", value)
	return f"+{digits}" if digits else value


def _website(settings: dict) -> dict:
	# `name` is what Google puts beside the results, and `alternateName` is where
	# the domain goes. Without the second one Google has no sanctioned place to
	# record that "reloop.pk" is the same thing as "reloop", and it falls back to
	# printing the host in the title line -- which is what it was doing.
	#
	# The pair is only a request, not a command: Google decides what to display
	# from this plus its own signals, and a change here needs a re-crawl to show
	# up. It is on the home page's graph on purpose -- that is the page Google
	# reads the site name from.
	host = urlparse(site_url("/")).netloc
	return {
		"@type": "WebSite",
		"@id": f"{site_url('/')}#website",
		"url": site_url("/"),
		"name": settings["shop_name"],
		"alternateName": host,
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
	# brand / gtin / mpn are all optional to Google, and all three are claims about
	# a specific physical item. Emitted only when the catalogue actually carries one:
	# guessing a brand from the product name is how a catalogue ends up attributing
	# goods to the wrong manufacturer.
	if brand := (product.get("brand") or "").strip():
		node["brand"] = {"@type": "Brand", "name": brand}
	for field, key in (("gtin", "gtin"), ("mpn", "mpn")):
		if value := (product.get(field) or "").strip():
			node[key] = value
	condition = (product.get("condition") or "").strip()
	if condition and condition.lower() not in ("", "new", "preloved"):
		node["itemCondition"] = "https://schema.org/UsedCondition"
		if not product.get("brand"):
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
		# Deliberately NOT emitting a compare-at here, which is where this used to put
		# one as an Offer.priceSpecification. Google rejected the whole Offer for it and
		# reported the Product as having no offers at all, on all 11 products -- every
		# one of them had a compare-at, so every one of them lost the property.
		#
		# priceSpecification is not a "was" price. On an Offer, schema.org means the
		# components that make up the price -- tax, shipping, discounts -- and Google's
		# merchant documentation reads it that way. A bare UnitPriceSpecification
		# carrying a single price contradicts the Offer's own price beside it.
		#
		# There is also nowhere correct to put it: schema.org has no "was" price on an
		# Offer. The storefront shows the struck-through figure itself, which is what a
		# shopper sees; this only ever mattered to a crawler reading markup, and a
		# crawler was reading it as a broken Offer.
		node["offers"] = offer
	# Merchant-listing properties. Both are optional per Google and both are claims
	# about how the business trades, so each is emitted only once the underlying
	# number is actually configured. Emitting a rate or a returns window that no one
	# entered would be inventing a policy and printing it beside the price.
	if shipping := _shipping_details(settings):
		node["shippingDetails"] = shipping
	if policy := _return_policy(settings):
		node["hasMerchantReturnPolicy"] = policy
	aggregate, entries = _ratings(product)
	if aggregate:
		node["aggregateRating"] = aggregate
		if entries:
			node["review"] = entries
	return node


def _shipping_details(settings: dict) -> dict | None:
	"""OfferShippingDetails, built from the shop's real configured rates.

	The destination is required by Google but must not be invented, so it is left
	out when the shop has not said where it ships to.

	shippingRate is the flat rate the shop actually charges. It stays the flat rate
	even when there is a free-shipping threshold, because the threshold is a
	minimum-order condition rather than the rate: reporting 0.00 would claim every
	order ships free, which is false for a 799 order under a 5000 threshold.
	"""
	if not _number(settings.get("flat_shipping_rate")):
		return None
	currency = settings["currency"]
	node = {
		"@type": "OfferShippingDetails",
		"shippingRate": {
			"@type": "MonetaryAmount",
			"value": _decimal(settings["flat_shipping_rate"]),
			"currency": currency,
		},
	}
	if _number(settings.get("free_shipping_above")):
		node["shippingDestination"] = {
			"@type": "DefinedRegion",
			"addressCountry": _country_code(settings.get("address_country")) or "PK",
		}
	return node


def _return_policy(settings: dict) -> dict | None:
	"""MerchantReturnPolicy, but only when a return window has been configured.

	The homepage advertises "14 day returns" as theme copy. That string is not
	configuration, so it cannot be promoted into structured data that Google may show
	to a shopper as a stated policy -- the number has to come from Shop Settings.
	"""
	days = settings.get("return_window_days")
	if not days or not str(days).strip().lstrip("-").isdigit():
		return None
	days = int(days)
	if days <= 0:
		return None
	return {
		"@type": "MerchantReturnPolicy",
		"applicableCountry": _country_code(settings.get("address_country")) or "PK",
		"returnPolicyCategory": "https://schema.org/MerchantReturnFiniteReturnWindow",
		"merchantReturnDays": days,
		"returnMethod": "https://schema.org/ReturnByMail",
		"returnFees": "https://schema.org/FreeReturn",
	}


def _ratings(product: dict) -> tuple[dict | None, list[dict]]:
	"""aggregateRating and review, or nothing at all when there are no reviews.

	Fabricated stars are a policy violation, not a cosmetic gap, so this reports
	only ratings that exist in Shop Review. With an empty table both are None and
	neither property is emitted.
	"""
	name = product.get("name")
	if not name or not frappe.db.exists("Shop Review", {"product": name}):
		return None, []
	from shop.storefront import reviews

	summary = reviews.summary(name)
	if not summary.get("count"):
		return None, []
	aggregate = {
		"@type": "AggregateRating",
		"ratingValue": summary["average"],
		"reviewCount": summary["count"],
		"bestRating": 5,
		"worstRating": 1,
	}
	rows = frappe.get_all(
		"Shop Review",
		filters={"product": name},
		fields=["reviewer_name", "rating", "title", "review"],
		order_by="creation desc",
		limit=5,
	)
	out = []
	for row in rows:
		if not (row.get("review") or "").strip():
			continue
		entry = {
			"@type": "Review",
			"reviewRating": {
				"@type": "Rating",
				"ratingValue": row["rating"],
				"bestRating": 5,
				"worstRating": 1,
			},
			"author": {"@type": "Person", "name": row.get("reviewer_name") or "Customer"},
			"datePublished": str(row.get("creation") or "")[:10],
			"reviewBody": row["review"],
		}
		if (row.get("title") or "").strip():
			entry["name"] = row["title"]
		out.append(entry)
	return aggregate, out


def _number(value) -> float | None:
	try:
		number = float(value)
	except (TypeError, ValueError):
		return None
	return number if number > 0 else None


def _decimal(value) -> str:
	return f"{float(value):.2f}"


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
	for row in products:
		route = row.get("route") or f"/product/{row.get('slug') or row.get('name')}"
		# Reuse the product-page builder rather than restating it. This catalog used to
		# describe products a second time, differently, and the two drifted: the pages
		# carried offers/review/aggregateRating and this carried none, so Google read
		# every item here as a Product with no offers and rejected all of them.
		# One builder means the homepage and a product page cannot disagree again.
		items.append(_product_node(row, settings))
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
	# The share card: the site's own lockup, wallpaper and spec strip at 1200x630,
	# the size every scraper expects. It replaced an auto-generated screenshot of
	# the page, which went stale the moment the hero copy changed -- a shared link
	# showed "Made properly" beside a site that says "Collected properly".
	#
	# A product photo still wins where there is one, so sharing a product shows
	# the product rather than the shop card.
	product_image = (product or {}).get("image")
	image = site_url(product_image or OG_DEFAULT_IMAGE)

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

	# Dimensions and alt, but only for the shop card. They are what a scraper
	# uses to lay a card out before it has fetched the image, and several render
	# a blank box rather than guess. They are NOT declared for a product photo:
	# product images are whatever the camera produced, and stating the card's
	# 1200x630 for one would be a lie the scraper acts on.
	if not product_image:
		metatags["og:image:width"] = str(OG_CARD_WIDTH)
		metatags["og:image:height"] = str(OG_CARD_HEIGHT)
		metatags["og:image:alt"] = f"{settings['shop_name']} — everyday essentials, new and preloved"

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
