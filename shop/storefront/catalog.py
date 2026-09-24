import frappe
from frappe.utils import cint, flt

from shop.storefront import pricing, stock

MAX_PAGE_SIZE = 60
MAX_CATALOG_SIZE = 500

SORT_ORDERS = {
	"ranking": "ranking desc, modified desc",
	"newest": "creation desc",
	"name": "product_name asc",
	"price_asc": None,
	"price_desc": None,
}

# Variant attributes the listing can filter on, keyed by the query parameter.
FACET_ATTRIBUTES = {"size": "size", "color": "color", "colour": "color"}
FACET_ORDER = ("size", "color")


@frappe.whitelist(allow_guest=True)
def get_products(
	collection: str | None = None,
	search: str | None = None,
	sort: str = "ranking",
	start: int = 0,
	limit: int = 24,
	price_min: float | None = None,
	price_max: float | None = None,
	in_stock: bool = False,
	size: str | None = None,
	color: str | None = None,
	with_facets: bool = False,
) -> dict:
	filters = {"published": 1}
	if collection:
		filters["name"] = ["in", collection_members(collection)]
	products = frappe.get_all(
		"Shop Product",
		filters=filters,
		or_filters=search_filters(search),
		fields=[
			"name",
			"product_name",
			"slug",
			"short_description",
			"has_variants",
			"item",
			"compare_at_price",
		],
		order_by=SORT_ORDERS.get(sort) or SORT_ORDERS["ranking"],
		limit=MAX_CATALOG_SIZE,
	)
	decorate(products)
	# Facets describe the category itself — the sizes and colours it stocks —
	# so they are computed from the searched collection before the price and
	# stock filters narrow it: capping the price must not make the Size group
	# disappear while a size filter is still on. They are likewise computed
	# before the size/colour filters apply, so a shopper who picked Large
	# still sees the other sizes to switch to.
	attributes: dict = {}
	facet_names: dict = {}
	if size or color or with_facets:
		attributes, facet_names = product_attributes(products)
	facets = facet_options(products, attributes, facet_names) if with_facets else None
	products = apply_post_filters(products, price_min, price_max, in_stock)
	if size:
		products = [p for p in products if matches_facet(attributes, p, "size", size)]
	if color:
		products = [p for p in products if matches_facet(attributes, p, "color", color)]
	if sort in ("price_asc", "price_desc"):
		products.sort(key=lambda p: p.price if p.price is not None else float("inf"))
		if sort == "price_desc":
			products.reverse()
	start = cint(start)
	limit = min(cint(limit) or 24, MAX_PAGE_SIZE)
	result = {"products": products[start : start + limit], "total": len(products)}
	if with_facets:
		result["facets"] = facets
	return result


def product_attributes(products: list) -> tuple[dict, dict]:
	"""Facet values per product, taken from its enabled variants.

	Returns ``({product name: {facet: [values]}}, {facet: attribute name})``.
	A product without variants has no entry, so filtering by size naturally
	leaves simple products out — there is no size to match, which is what a
	shopper asking for "Large" means. The attribute's own name is kept so the
	filter bar can label the group the way the product page does (Colour)."""
	templates = [p.item for p in products if p.has_variants]
	if not templates:
		return {}, {}
	children = frappe.get_all(
		"Item",
		filters={"variant_of": ["in", templates], "disabled": 0},
		fields=["name", "variant_of"],
	)
	if not children:
		return {}, {}
	rows = frappe.get_all(
		"Item Variant Attribute",
		filters={"parent": ["in", [child.name for child in children]]},
		fields=["parent", "attribute", "attribute_value"],
	)
	owner = {child.name: child.variant_of for child in children}
	template_product = {p.item: p.name for p in products if p.has_variants}
	used: dict[tuple[str, str], set] = {}
	names: dict[str, str] = {}
	for row in rows:
		facet = FACET_ATTRIBUTES.get((row.attribute or "").strip().lower())
		value = (row.attribute_value or "").strip()
		if not facet or not value:
			continue
		product = template_product.get(owner.get(row.parent))
		if not product:
			continue
		names.setdefault(facet, row.attribute)
		used.setdefault((product, facet), set()).add(value)
	attributes = {}
	for (product, facet), values in used.items():
		attributes.setdefault(product, {})[facet] = sorted(values, key=str.casefold)
	return attributes, names


def facet_options(products: list, attributes: dict, names: dict) -> dict:
	"""``{facet: {"attribute", "values"}}`` for the products in scope.

	Facets with no options are left out entirely, which is how a category
	without variants ends up with no Size or Colour filter at all."""
	from shop.storefront.product import ordered_values

	facets = {}
	for facet in FACET_ORDER:
		values: set = set()
		for product in products:
			values.update(attributes.get(product.name, {}).get(facet) or [])
		if not values:
			continue
		attribute = names.get(facet, facet.title())
		ordered = [value for value in ordered_values(attribute) if value in values]
		ordered += sorted(values - set(ordered), key=str.casefold)
		facets[facet] = {"attribute": attribute, "values": ordered}
	return facets


def matches_facet(attributes: dict, product, facet: str, wanted: str) -> bool:
	return wanted.casefold() in {
		value.casefold() for value in attributes.get(product.name, {}).get(facet) or []
	}


def apply_post_filters(products, price_min, price_max, in_stock):
	def keep(product):
		if price_min is not None and (product.price is None or product.price < flt(price_min)):
			return False
		if price_max is not None and (product.price is None or product.price >= flt(price_max)):
			return False
		if in_stock and not product.in_stock:
			return False
		return True

	return [product for product in products if keep(product)]


@frappe.whitelist(allow_guest=True)
def get_collections() -> list[dict]:
	collections = frappe.get_all(
		"Shop Collection",
		filters={"published": 1},
		fields=["name", "title", "slug", "description", "image"],
		order_by="ranking desc, title asc",
	)
	counts = collection_counts([c.name for c in collections])
	for row in collections:
		row.route = f"/collection/{row.slug}"
		row.product_count = counts.get(row.name, 0)
		row.image_css = tile_background(row.image)
	return collections


def tile_background(image: str | None) -> str | None:
	if not image:
		return None
	return f"url('{image}')"


def collection_members(slug: str) -> list[str]:
	collection = frappe.db.get_value("Shop Collection", {"slug": slug, "published": 1})
	if not collection:
		return []
	return frappe.get_all(
		"Shop Product Collection", filters={"collection": collection}, pluck="parent"
	)


def collection_counts(collections: list[str]) -> dict:
	if not collections:
		return {}
	from collections import Counter

	rows = frappe.get_all(
		"Shop Product Collection",
		filters={"collection": ["in", collections]},
		pluck="collection",
	)
	return Counter(rows)


def search_filters(search: str | None) -> list | None:
	if not search:
		return None
	term = f"%{search.strip()}%"
	return [
		["product_name", "like", term],
		["short_description", "like", term],
		["item", "like", term],
	]


def decorate(products: list) -> None:
	from shop.storefront import reviews

	images = first_images([p.name for p in products])
	prices = display_prices(products)
	availability = display_stock(products)
	ratings = reviews.summaries([p.name for p in products])
	for product in products:
		product.route = f"/product/{product.slug}"
		product.image = images.get(product.name)
		price = prices.get(product.item, {})
		product.price = price.get("rate")
		product.formatted_price = price.get("formatted")
		product.in_stock = availability.get(product.item, False)
		apply_compare_at(product, product.price)
		rating = ratings.get(product.name)
		product.rating_average = rating["average"] if rating else None
		product.rating_count = rating["count"] if rating else 0
		product.rating_stars = star_string(rating["average"]) if rating else None


def apply_compare_at(target, price) -> None:
	compare_at = flt(target.get("compare_at_price"))
	if not price or compare_at <= flt(price):
		target["compare_at_price"] = None
		return
	target["formatted_compare_at"] = pricing.format_amount(compare_at)
	target["discount_pct"] = round((compare_at - flt(price)) * 100 / compare_at)
	target["formatted_savings"] = pricing.format_amount(compare_at - flt(price))


def star_string(average: float) -> str:
	full = int(flt(average) + 0.5)
	return "★" * full + "☆" * (5 - full)


def first_images(product_names: list[str]) -> dict:
	if not product_names:
		return {}
	rows = frappe.get_all(
		"Shop Product Image",
		filters={"parent": ["in", product_names]},
		fields=["parent", "image"],
		order_by="parent, idx",
	)
	images = {}
	for row in rows:
		images.setdefault(row.parent, row.image)
	return images


def display_prices(products: list) -> dict:
	simple = [p.item for p in products if not p.has_variants]
	templates = [p.item for p in products if p.has_variants]
	prices = pricing.get_prices(simple)
	for template, codes in variants_by_template(templates).items():
		rates = [p["rate"] for code, p in pricing.get_prices(codes).items()]
		if rates:
			prices[template] = {"rate": min(rates), "formatted": pricing.format_amount(min(rates))}
	return prices


def display_stock(products: list) -> dict:
	settings = frappe.get_cached_doc("Shop Settings")
	if settings.allow_out_of_stock:
		return dict.fromkeys([p.item for p in products], True)
	simple = [p.item for p in products if not p.has_variants]
	availability = {code: qty > 0 for code, qty in stock.get_stock(simple).items()}
	templates = [p.item for p in products if p.has_variants]
	for template, codes in variants_by_template(templates).items():
		availability[template] = any(qty > 0 for qty in stock.get_stock(codes).values())
	return availability


def variants_by_template(templates: list[str]) -> dict[str, list[str]]:
	if not templates:
		return {}
	rows = frappe.get_all(
		"Item", filters={"variant_of": ["in", templates]}, fields=["name", "variant_of"]
	)
	grouped = {}
	for row in rows:
		grouped.setdefault(row.variant_of, []).append(row.name)
	return grouped
