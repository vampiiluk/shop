import re
from urllib.parse import quote

import frappe

from shop.phone import chat_url
from shop.storefront import images, pricing, stock


@frappe.whitelist(allow_guest=True)
def get_product(slug: str) -> dict:
	name = frappe.db.get_value("Shop Product", {"slug": slug, "published": 1})
	if not name:
		frappe.throw(frappe._("Product not found"), frappe.DoesNotExistError)
	doc = frappe.get_doc("Shop Product", name)
	from shop.storefront import reviews

	payload = {
		"name": doc.name,
		"product_name": doc.product_name,
		"slug": doc.slug,
		"item": doc.item,
		"short_description": doc.short_description,
		"condition": (doc.condition or "").strip(),
		"description": doc.description,
		"has_variants": doc.has_variants,
		"compare_at_price": doc.compare_at_price,
		"highlights": [
			{"label": line.strip()} for line in (doc.highlights or "").splitlines() if line.strip()
		],
		"images": images.product_images(doc),
		"collections": product_collections(doc),
		"rating": reviews.summary(doc.name),
	}
	if doc.has_variants:
		payload.update(variant_details(doc.item, doc.compare_at_price))
	else:
		price = pricing.get_price(doc.item) or {}
		payload.update(
			{
				"price": price.get("rate"),
				"formatted_price": price.get("formatted"),
				"in_stock": stock.is_in_stock(doc.item),
			}
		)
	from shop.storefront.catalog import apply_compare_at, star_string

	apply_compare_at(payload, payload.get("price"))
	if payload["rating"]["count"]:
		payload["rating"]["stars"] = star_string(payload["rating"]["average"])
	payload["whatsapp_url"] = store_whatsapp_url(doc)
	return payload


def store_whatsapp_url(doc) -> str:
	"""wa.me chat about this product with name and link prefilled, or ''.

	The store's number comes from the WhatsApp business number in Settings,
	which is where it is meant to be maintained. Pickup locations are only a
	fallback, for a store that has set the number but left a location phone
	behind from before. With no number anywhere the key is '' and the
	storefront's Buy on WhatsApp button hides itself (its visibility condition
	is falsy)."""
	from shop.storefront import pickup
	from shop.storefront.urls import SITE_BASE

	settings = frappe.get_cached_doc("Shop Settings")
	number = (settings.get("whatsapp_number") or "").strip()
	if not number:
		default = (settings.get("default_pickup_location") or "").strip()
		rows = [
			row for row in pickup.configured(settings) if row.get("whatsapp_url")
		]
		chosen = next((row for row in rows if row["name"] == default), None) or (
			rows[0] if rows else None
		)
		if not chosen:
			return ""
		base = chosen["whatsapp_url"]
	else:
		base = chat_url(number)
	product_url = f"{SITE_BASE}/product/{doc.slug}"
	message = f"Hi! I'm interested in {doc.product_name or doc.name} — {product_url}"
	return f"{base}?text={quote(message)}"


def product_collections(doc) -> list[dict]:
	collections = [row.collection for row in doc.collections]
	if not collections:
		return []
	return frappe.get_all(
		"Shop Collection",
		filters={"name": ["in", collections], "published": 1},
		fields=["title", "slug"],
	)


def variant_details(template: str, compare_at: float | None = None) -> dict:
	variants = load_variants(template, compare_at)
	rates = [v["price"] for v in variants if v["price"] is not None]
	default = next((v for v in variants if v["in_stock"]), variants[0] if variants else None)
	return {
		"attributes": attribute_options(template, variants),
		"variants": variants,
		"price": min(rates) if rates else None,
		"formatted_price": pricing.format_amount(min(rates)) if rates else None,
		"in_stock": any(v["in_stock"] for v in variants),
		"default_item_code": default["item_code"] if default else None,
	}


def load_variants(template: str, compare_at: float | None = None) -> list[dict]:
	rows = frappe.get_all(
		"Item", filters={"variant_of": template, "disabled": 0}, fields=["name", "image"]
	)
	items = [row.name for row in rows]
	images = {row.name: row.image for row in rows if row.image}
	prices = pricing.get_prices(items)
	attributes = frappe.get_all(
		"Item Variant Attribute",
		filters={"parent": ["in", items]},
		fields=["parent", "attribute", "attribute_value"],
	)
	variants = []
	for item_code in items:
		price = prices.get(item_code, {})
		variants.append(
			{
				"item_code": item_code,
				"attributes": {
					row.attribute: row.attribute_value for row in attributes if row.parent == item_code
				},
				"price": price.get("rate"),
				"formatted_price": price.get("formatted"),
				"in_stock": stock.is_in_stock(item_code),
				"image": images.get(item_code),
				**variant_savings(price.get("rate"), compare_at),
			}
		)
	return variants


def variant_savings(rate: float | None, compare_at: float | None) -> dict:
	from frappe.utils import flt

	if not rate or not compare_at or flt(compare_at) <= flt(rate):
		return {"formatted_savings": None, "discount_pct": None}
	saved = flt(compare_at) - flt(rate)
	return {
		"formatted_savings": pricing.format_amount(saved),
		"discount_pct": round(saved * 100 / flt(compare_at)),
	}


def attribute_options(template: str, variants: list[dict]) -> list[dict]:
	order = frappe.get_all(
		"Item Variant Attribute",
		filters={"parent": template},
		fields=["attribute"],
		order_by="idx",
		pluck="attribute",
	)
	options = []
	for attribute in order:
		values = ordered_values(attribute)
		used = {v["attributes"].get(attribute) for v in variants}
		options.append(
			{"attribute": attribute, "values": [v for v in values if v in used]}
		)
	return options


def ordered_values(attribute: str) -> list[str]:
	"""The attribute's values in the order the storefront offers them.

	Stored `idx` order is the intent, so it is what we use - except when the
	attribute carries numbers. Sizes like 36, 41.5 and 38-39 are only ever
	appended as they are added, which leaves the picker reading 40, 38, 36, 37,
	39. Sorting those by size keeps the picker ascending no matter what order
	the values were entered in.
	"""
	values = frappe.get_all(
		"Item Attribute Value",
		filters={"parent": attribute},
		order_by="idx",
		pluck="attribute_value",
	)
	return sorted(values, key=size_order) if any(measures_a_size(v) for v in values) else values


def measures_a_size(value: str) -> bool:
	"""True when `value` is a number or a number range, so it has a size to compare."""
	text = str(value).strip()
	return bool(SIZE_NUMBER.fullmatch(text) or SIZE_RANGE.fullmatch(text))


SIZE_NUMBER = re.compile(r"\d+(?:\.\d+)?")
# Only the lower bound is captured: the decimal part of each number is
# non-capturing so group(1) is the whole bound rather than ".5" or None.
SIZE_RANGE = re.compile(r"(\d+(?:\.\d+)?)\s*[-–/]\s*\d+(?:\.\d+)?")

# Named sizes keep the lead - Extra Small through Extra Large read in that order
# whatever the rows say - then plain numbers, then ranges by their lower bound.
NAMED_SIZES = {
	"xxs": 0,
	"xs": 1,
	"extra small": 1,
	"s": 2,
	"small": 2,
	"m": 3,
	"medium": 3,
	"l": 4,
	"large": 4,
	"xl": 5,
	"extra large": 5,
	"xxl": 6,
	"xxxl": 7,
	"one size": 8,
}


def size_order(value: str) -> tuple[int, float, str]:
	"""Sort key placing values into named, plain-number, then range groups."""
	text = str(value).strip()
	lowered = text.lower()
	if lowered in NAMED_SIZES:
		return (0, float(NAMED_SIZES[lowered]), lowered)
	if SIZE_NUMBER.fullmatch(text):
		return (1, float(text), lowered)
	span = SIZE_RANGE.fullmatch(text)
	if span:
		return (2, float(span.group(1)), lowered)
	return (3, 0.0, lowered)
