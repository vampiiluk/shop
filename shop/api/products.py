import csv
import html
import io
import re

import frappe
from frappe import _
from frappe.utils import cint, flt, get_url, now_datetime, strip_html
from frappe.website.utils import cleanup_page_name

from shop.api import only_managers
from shop.storefront import pricing, stock


@frappe.whitelist()
def get_products(
	search: str | None = None, status: str | None = None, start: int = 0, limit: int = 20
) -> dict:
	only_managers()
	filters = {}
	if status == "published":
		filters["published"] = 1
	elif status == "draft":
		filters["published"] = 0
	or_filters = None
	if search:
		term = f"%{search.strip()}%"
		or_filters = [["product_name", "like", term], ["slug", "like", term], ["item", "like", term]]
	products = frappe.get_all(
		"Shop Product",
		filters=filters,
		or_filters=or_filters,
		fields=["name", "product_name", "slug", "item", "published", "ranking", "has_variants"],
		order_by="ranking desc, modified desc",
		start=cint(start),
		limit=min(cint(limit) or 20, 100),
	)
	decorate(products)
	return {"products": products, "total": frappe.db.count("Shop Product", filters=filters)}


# The columns a Marketplace import expects, in this order. The CSV is meant to
# be handed to Facebook's catalogue tool as it is, so the header is not quoted
# and the price is written as a bare number.
EXPORT_COLUMNS = [
	"Title",
	"Price",
	"Category",
	"Condition",
	"Description",
	"Size",
	"Material",
	"Images",
]

# The shop records what it knows - "New" or "Preloved" - while a Marketplace
# import only accepts New / Used - Like New / Used - Good / Used - Fair.
# Preloved is a used item in saleable condition, so it is called "Used -
# Good" rather than claiming to be like new, which would be a stronger claim
# than the shop has made. Unknown wording is passed through untouched.
CONDITION_LABELS = {
	"new": "New",
	"brand new": "New",
	"preloved": "Used - Good",
	"pre-owned": "Used - Good",
	"pre owned": "Used - Good",
	"used": "Used - Good",
	"used - good": "Used - Good",
	"used - like new": "Used - Like New",
	"like new": "Used - Like New",
	"used - fair": "Used - Fair",
}

_BLOCK_TAG = re.compile(r"(?i)<(?:br|/p|/div|/li|/h[1-6])\s*/?>")


@frappe.whitelist(methods=["POST"])
def export_csv(names) -> None:
	"""Download the chosen products as a CSV for a Marketplace import.

	Only the products that were ticked are exported; this is not a catalogue
	dump, so nothing leaves the shop that the merchant did not pick.
	"""
	only_managers()
	content = build_export_csv(names)
	frappe.local.response.filename = f"products_{now_datetime():%Y%m%d_%H%M%S}.csv"
	frappe.local.response.filecontent = content.encode("utf-8")
	frappe.local.response.type = "download"


def build_export_csv(names) -> str:
	names = _selected_names(names)
	if not names:
		frappe.throw(_("Select at least one product to export"))

	products = frappe.get_all(
		"Shop Product",
		filters={"name": ["in", names]},
		fields=["name", "product_name", "condition", "description", "item", "has_variants"],
		limit_page_length=0,
	)
	by_name = {row.name: row for row in products}
	rows = [by_name[name] for name in names if name in by_name]
	if not rows:
		frappe.throw(_("The selected products no longer exist"))
	found = [row.name for row in rows]

	images = _grouped_values("Shop Product Image", found, "image")
	collections = _grouped_values("Shop Product Collection", found, "collection")
	option_sizes: dict[str, list[str]] = {}
	for option in frappe.get_all(
		"Shop Product Option",
		filters={"parent": ["in", found]},
		fields=["parent", "attribute", "values"],
		order_by="parent, idx",
		limit_page_length=0,
	):
		if option.attribute == "Size" and option.values:
			option_sizes.setdefault(option.parent, []).extend(_split_values(option.values))

	variant_codes: dict[str, list[str]] = {}
	variant_parents = [row.item for row in rows if row.has_variants]
	if variant_parents:
		for variant in frappe.get_all(
			"Item",
			filters={"variant_of": ["in", variant_parents]},
			fields=["name", "variant_of"],
			limit_page_length=0,
		):
			variant_codes.setdefault(variant.variant_of, []).append(variant.name)

	size_values: dict[str, list[str]] = {}
	all_variants = [code for codes in variant_codes.values() for code in codes]
	if all_variants:
		for attribute in frappe.get_all(
			"Item Variant Attribute",
			filters={"parent": ["in", all_variants], "attribute": "Size"},
			fields=["parent", "attribute_value"],
			order_by="parent, idx",
			limit_page_length=0,
		):
			if attribute.attribute_value:
				size_values.setdefault(attribute.parent, []).append(attribute.attribute_value)

	codes_by_product = {
		row.name: variant_codes.get(row.item, []) if row.has_variants else [row.item] for row in rows
	}
	prices = pricing.get_prices([code for codes in codes_by_product.values() for code in codes])

	collection_names = {name for names_in_product in collections.values() for name in names_in_product}
	collection_titles = (
		{
			collection.name: collection.title
			for collection in frappe.get_all(
				"Shop Collection",
				filters={"name": ["in", list(collection_names)]},
				fields=["name", "title"],
				limit_page_length=0,
			)
		}
		if collection_names
		else {}
	)

	buffer = io.StringIO()
	# QUOTE_NONNUMERIC quotes every text field, including one that is empty,
	# and leaves the price bare - the shape the sample has.
	buffer.write(",".join(EXPORT_COLUMNS) + "\r\n")
	writer = csv.writer(buffer, quoting=csv.QUOTE_NONNUMERIC, lineterminator="\r\n")

	for row in rows:
		codes = codes_by_product[row.name]
		rates = [
			prices[code]["rate"]
			for code in codes
			if code in prices and prices[code].get("rate") is not None
		]

		if row.has_variants:
			sizes = {value for code in codes for value in size_values.get(code, [])}
		else:
			sizes = set()
		if not sizes:
			# A product that does not vary still records the range it is made
			# in on its options; that range is the best size information there is.
			sizes = set(option_sizes.get(row.name, []))

		categories = list(
			dict.fromkeys(
				collection_titles.get(name) or name for name in collections.get(row.name, [])
			)
		)
		image_urls = list(
			dict.fromkeys(get_url(image) for image in images.get(row.name, []) if image)
		)

		writer.writerow(
			[
				row.product_name,
				_csv_price(min(rates) if rates else None),
				", ".join(categories),
				CONDITION_LABELS.get(
					(row.condition or "").strip().lower(), (row.condition or "").strip()
				),
				_plain_text(row.description),
				", ".join(sorted(sizes, key=_natural_key)),
				"",
				", ".join(image_urls),
			]
		)

	return buffer.getvalue()


def _selected_names(names) -> list[str]:
	"""The ticked product names, deduplicated and in the order they were picked."""
	if isinstance(names, str):
		names = names.split(",")
	selected = []
	seen = set()
	for name in names or []:
		name = str(name).strip()
		if name and name not in seen:
			seen.add(name)
			selected.append(name)
	return selected


def _grouped_values(doctype: str, parents: list[str], field: str) -> dict[str, list[str]]:
	grouped: dict[str, list[str]] = {}
	for row in frappe.get_all(
		doctype,
		filters={"parent": ["in", parents]},
		fields=["parent", field],
		order_by="parent, idx",
		limit_page_length=0,
	):
		value = row.get(field)
		if value:
			grouped.setdefault(row.parent, []).append(value)
	return grouped


def _split_values(values: str) -> list[str]:
	return [value.strip() for value in str(values).split(",") if value.strip()]


def _plain_text(value: str | None) -> str:
	"""The description as one line of readable text.

	The shop stores it as HTML. Block tags become spaces before they are
	stripped so two paragraphs do not run together, and entities such as
	&amp; are put back.
	"""
	if not value:
		return ""
	text = _BLOCK_TAG.sub(" ", value)
	text = html.unescape(strip_html(text))
	return re.sub(r"\s+", " ", text).strip()


def _csv_price(rate) -> int | float | str:
	if rate is None:
		return ""
	amount = round(flt(rate), 2)
	return int(amount) if amount == int(amount) else amount


def _natural_key(value: str) -> list[tuple[int, float | str]]:
	"""Sort sizes the way a person reads them: 40 before 100, 40.5 after 40."""
	parts = re.split(r"(\d+(?:\.\d+)?)", str(value))
	return [
		(0, float(part)) if re.fullmatch(r"\d+(?:\.\d+)?", part) else (1, part.lower())
		for part in parts
		if part
	]


def display_names(item_codes: list[str]) -> dict[str, str]:
	"""Human names for items; variants become "Parent · Value / Value" instead of code-ish item names."""
	if not item_codes:
		return {}
	items = frappe.get_all(
		"Item", filters={"name": ["in", item_codes]}, fields=["name", "item_name", "variant_of"]
	)
	parents = {item.variant_of for item in items if item.variant_of}
	parent_names = {
		row.name: row.item_name
		for row in frappe.get_all("Item", filters={"name": ["in", list(parents)]}, fields=["name", "item_name"])
	} if parents else {}
	values = {}
	for row in frappe.get_all(
		"Item Variant Attribute",
		filters={"parent": ["in", [item.name for item in items if item.variant_of]]},
		fields=["parent", "attribute_value"],
		order_by="idx",
	):
		values.setdefault(row.parent, []).append(row.attribute_value)
	names = {}
	for item in items:
		if item.variant_of and values.get(item.name):
			names[item.name] = f"{parent_names.get(item.variant_of, item.variant_of)} · {' / '.join(values[item.name])}"
		else:
			names[item.name] = item.item_name
	return names

def decorate(products: list) -> None:
	for product in products:
		product["image"] = frappe.db.get_value(
			"Shop Product Image", {"parent": product.name}, "image", order_by="idx"
		)
		codes = sellable_codes(product.item, product.has_variants)
		prices = pricing.get_prices(codes)
		rates = [entry["rate"] for entry in prices.values()]
		product["formatted_price"] = pricing.format_amount(min(rates)) if rates else None
		product["stock"] = sum(stock.get_stock(codes).values())


def item_labels(codes: list[str]) -> tuple[dict[str, str], dict[str, list[str]]]:
	"""A human name for each item, and the attributes that pick the variant.

	A variant's own name is a code with the size on the end - "CMP ALKHESTE
	LOW-414" - which tells a customer nothing about what they ordered. So
	the product's own name is given, and under it the size or colour that
	was actually picked.

	The template of a variant carries a row of its own with no value, which
	is the size range it is made in rather than a size anyone chose, so
	those are left out.
	"""
	names: dict[str, str] = {}
	attributes: dict[str, list[str]] = {}
	if not codes:
		return names, attributes

	items = frappe.get_all(
		"Item", filters={"name": ["in", codes]}, fields=["name", "item_name", "variant_of"]
	)
	parents = {row.variant_of for row in items if row.variant_of}
	parent_names = {}
	if parents:
		parent_names = {
			row.name: row.item_name
			for row in frappe.get_all(
				"Item", filters={"name": ["in", list(parents)]}, fields=["name", "item_name"]
			)
		}
	for row in items:
		if row.variant_of:
			names[row.name] = parent_names.get(row.variant_of) or row.item_name
		else:
			names[row.name] = row.item_name

	for row in frappe.get_all(
		"Item Variant Attribute",
		filters={"parent": ["in", codes]},
		fields=["parent", "attribute", "attribute_value"],
		order_by="idx",
	):
		if not row.attribute_value:
			continue
		attributes.setdefault(row.parent, []).append(f"{row.attribute}: {row.attribute_value}")

	return names, attributes


def sellable_codes(item: str, has_variants: bool) -> list[str]:
	if has_variants:
		return frappe.get_all("Item", filters={"variant_of": item}, pluck="name")
	return [item]


@frappe.whitelist()
def get_product(name: str) -> dict:
	only_managers()
	doc = frappe.get_doc("Shop Product", name)
	codes = sellable_codes(doc.item, doc.has_variants)
	prices = pricing.get_prices(codes)
	stock_map = stock.get_stock(codes)
	return {
		"name": doc.name,
		"item": doc.item,
		"product_name": doc.product_name,
		"slug": doc.slug,
		"published": doc.published,
		"ranking": doc.ranking,
		"short_description": doc.short_description,
		"description": doc.description,
		"compare_at_price": doc.compare_at_price,
		"highlights": doc.highlights,
		"condition": doc.condition,
		"has_variants": doc.has_variants,
		"images": [{"image": row.image, "alt_text": row.alt_text} for row in doc.images],
		"collections": [row.collection for row in doc.collections],
		"price": prices.get(doc.item, {}).get("rate") if not doc.has_variants else None,
		"variants": [
			{
				"item_code": code,
				"price": prices.get(code, {}).get("rate"),
				"stock": stock_map.get(code, 0),
			}
			for code in codes
		],
		"stock": sum(stock_map.values()),
		"meta_product_id": doc.meta_product_id or None,
		"meta_product_link": commerce_manager_url(doc.meta_product_id),
	}


def commerce_manager_url(meta_product_id: str | None) -> str | None:
	"""Link to the catalogue's product list in Commerce Manager.

	Meta exposes no verified per-product deep link (and the API token cannot
	read the business id), so point at the catalogue's products list — which
	is searchable by the numeric product id shown beside this link."""
	if not meta_product_id:
		return None
	catalog_id = (frappe.db.get_single_value("Shop Settings", "meta_catalog_id") or "").strip()
	if not catalog_id:
		return None
	return f"https://business.facebook.com/commerce/catalogs/{catalog_id}/products"


@frappe.whitelist(methods=["POST"])
def save_product(payload: dict) -> dict:
	only_managers()
	doc = (
		frappe.get_doc("Shop Product", payload["name"])
		if payload.get("name")
		else frappe.new_doc("Shop Product")
	)
	if not payload.get("name"):
		doc.item = payload["item"]
	doc.product_name = payload.get("product_name") or doc.product_name
	doc.short_description = payload.get("short_description")
	doc.description = payload.get("description")
	doc.compare_at_price = flt(payload.get("compare_at_price")) or None
	doc.highlights = payload.get("highlights")
	if "condition" in payload:
		# partial payloads (e.g. the agent tool) leave it untouched
		doc.condition = (payload.get("condition") or "").strip() or None
	doc.ranking = cint(payload.get("ranking"))
	doc.published = 1 if payload.get("published") else 0
	if payload.get("slug"):
		doc.slug = cleanup_page_name(payload["slug"])
	set_images(doc, payload.get("images"))
	set_collections(doc, payload.get("collections"))
	doc.save(ignore_permissions=True) if doc.get("name") and not doc.is_new() else doc.insert(
		ignore_permissions=True
	)
	if payload.get("price") is not None and not doc.has_variants:
		set_price(doc.item, flt(payload["price"]))
	return get_product(doc.name)


def set_images(doc, images) -> None:
	if images is None:
		return
	doc.images = []
	for image in images:
		url = image if isinstance(image, str) else image.get("image")
		if url:
			doc.append("images", {"image": url, "alt_text": doc.product_name})


def set_collections(doc, collections) -> None:
	if collections is None:
		return
	doc.collections = []
	for collection in collections:
		doc.append("collections", {"collection": collection})


def set_price(item_code: str, rate: float) -> None:
	settings = frappe.get_cached_doc("Shop Settings")
	name = frappe.db.get_value("Item Price", {"item_code": item_code, "price_list": settings.price_list})
	if name:
		frappe.db.set_value("Item Price", name, "price_list_rate", rate)
		return
	frappe.get_doc(
		{
			"doctype": "Item Price",
			"item_code": item_code,
			"price_list": settings.price_list,
			"price_list_rate": rate,
		}
	).insert(ignore_permissions=True)


@frappe.whitelist(methods=["POST"])
def create_product(
	product_name: str,
	price: float,
	description: str | None = None,
	short_description: str | None = None,
	compare_at_price: float | None = None,
	condition: str | None = None,
	opening_stock: float = 0,
	images: list | None = None,
	collections: list | None = None,
	published: bool = True,
) -> dict:
	"""Create the ERPNext Item, its price and stock, and the storefront product in one step."""
	only_managers()
	settings = frappe.get_cached_doc("Shop Settings")
	item_code = unique_item_code(product_name)
	frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": item_code,
			"item_name": product_name,
			"item_group": item_group(),
			"stock_uom": "Nos",
			"is_stock_item": 1,
			"description": short_description or product_name,
		}
	).insert(ignore_permissions=True)
	set_price(item_code, flt(price))
	if flt(opening_stock) > 0:
		receive_stock(item_code, flt(opening_stock), flt(price), settings)
	return save_product(
		{
			"item": item_code,
			"product_name": product_name,
			"short_description": short_description,
			"description": description,
			"compare_at_price": compare_at_price,
			"condition": condition,
			"images": images or [],
			"collections": collections or [],
			"published": published,
		}
	)


def unique_item_code(product_name: str) -> str:
	base = cleanup_page_name(product_name).upper()[:30] or "PRODUCT"
	code = base
	suffix = 2
	while frappe.db.exists("Item", code):
		code = f"{base}-{suffix}"
		suffix += 1
	return code


def item_group() -> str:
	for group in ("Products", "All Item Groups"):
		if frappe.db.exists("Item Group", group):
			return group
	return frappe.db.get_value("Item Group", {}, "name")


def receive_stock(item_code: str, qty: float, rate: float, settings) -> None:
	entry = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": "Material Receipt",
			"company": settings.company,
			"items": [
				{
					"item_code": item_code,
					"qty": qty,
					"t_warehouse": settings.default_warehouse,
					"basic_rate": rate * 0.6,
					"allow_zero_valuation_rate": 1,
				}
			],
		}
	)
	entry.flags.ignore_permissions = True
	entry.submit()


@frappe.whitelist(methods=["POST"])
def set_published(name: str, published: bool) -> None:
	only_managers()
	frappe.db.set_value("Shop Product", name, "published", 1 if published else 0)


@frappe.whitelist(methods=["POST"])
def delete_product(name: str) -> None:
	only_managers()
	for review in frappe.get_all("Shop Review", filters={"product": name}, pluck="name"):
		frappe.delete_doc("Shop Review", review, ignore_permissions=True, force=True)
	frappe.delete_doc("Shop Product", name, ignore_permissions=True)


@frappe.whitelist()
def get_collections() -> list[dict]:
	only_managers()
	collections = frappe.get_all(
		"Shop Collection",
		fields=["name", "title", "slug", "description", "image", "published", "ranking"],
		order_by="ranking desc, title asc",
	)
	for collection in collections:
		collection["product_count"] = frappe.db.count(
			"Shop Product Collection", {"collection": collection.name}
		)
	return collections


@frappe.whitelist(methods=["POST"])
def save_collection(payload: dict) -> None:
	only_managers()
	doc = (
		frappe.get_doc("Shop Collection", payload["name"])
		if payload.get("name")
		else frappe.new_doc("Shop Collection")
	)
	doc.title = payload["title"]
	doc.description = payload.get("description")
	doc.image = payload.get("image")
	doc.ranking = cint(payload.get("ranking"))
	doc.published = 1 if payload.get("published") else 0
	doc.save(ignore_permissions=True) if not doc.is_new() else doc.insert(ignore_permissions=True)


@frappe.whitelist(methods=["POST"])
def delete_collection(name: str) -> None:
	only_managers()
	frappe.delete_doc("Shop Collection", name, ignore_permissions=True)
