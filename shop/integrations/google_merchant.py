"""Google Merchant Center product feed.

Google fetches this file itself, on its own schedule, so every value has to be
current when it is asked for: prices from the shop's selling price list, stock
from the configured warehouse, and availability that matches what the product
page says. The feed is generated on request rather than stored, which is what
keeps it from drifting after a price change or a sale.

Shape, and why:

* RSS 2.0 with the ``g:`` namespace is the format Merchant Center documents for
  scheduled fetches. One ``<item>`` per sellable item: a simple product once, a
  variant product once per variant, with ``g:item_group_id`` tying the variants
  together. Google groups variants itself from that id; unlike Meta it does not
  need a parent row standing in for the group.
* ``g:id`` is the ERPNext item code, not the slug. The item code survives a
  rename of the product page; a slug can change, and Google would then treat the
  same physical product as a new one and throw away its history. Codes longer
  than Google's 50-character limit are replaced with a deterministic hash of the
  code, so the id is still stable.
* ``g:brand`` comes from ``Item.brand``, never from the store name. The shop
  sells authentic branded and unbranded goods; printing the shop name as the
  brand would be a false claim about who made them. Unbranded products simply
  omit the attribute.
* ``g:identifier_exists`` is ``no`` only when there is no validated GTIN and no
  MPN. The catalogue has no manufacturer part numbers, and a barcode is only a
  GTIN when its check digit is valid -- an arbitrary shop barcode under
  ``g:gtin`` would be rejected and could get the item disapproved.
* ``g:condition`` uses Merchant Center's enum, not the admin's free text:
  New -> new, Preloved/Used -> used, Refurbished -> refurbished.
* ``g:shipping`` reflects what the storefront actually charges. When no
  shipping account is configured the cart charges nothing, so the feed says
  free rather than inventing a rate. The configured free-shipping threshold is
  deliberately not folded into the per-item price: it applies to the order
  total, and claiming 0 on a single expensive item would be false as soon as
  the shopper adds a cheap one.
* ``g:returns`` is offer-level, so the return window travels with the product
  instead of depending on a Merchant Center account policy. The window is the
  one the shop actually enforces in ``shop.storefront.returns`` (14 days); a
  positive ``return_window_days`` setting overrides it. The feed does not
  invent a policy when neither is available -- no country means no returns
  block at all.

Products without a usable image or a positive price are left out: Google
requires both, and an item that cannot be listed validly is worse than an item
that is absent until the catalogue is fixed.
"""

import hashlib
import re
from html import unescape

import frappe
from frappe.utils import cint, flt

from shop.integrations.feed_images import image_link
from shop.storefront import catalog, images, pricing, stock
from shop.storefront.returns import RETURN_WINDOW_DAYS
from shop.storefront.urls import SITE_BASE

TITLE_LIMIT = 150
DESCRIPTION_LIMIT = 5000
ID_LIMIT = 50
GTIN_LENGTHS = (8, 12, 13, 14)

# ERPNext attribute names that map onto Merchant Center's core variant fields.
# Only these are sent: Merchant Center rejects an unknown variant attribute, and
# the shop's variant options are currently Size and Colour.
VARIANT_FIELDS = {
	"size": "size",
	"colour": "color",
	"color": "color",
	"material": "material",
	"pattern": "pattern",
}

# XML 1.0 forbids most C0 control characters, and Merchant Center also rejects
# invisible formatting characters such as zero-width joiners. Product copy is
# typed by hand and copied from suppliers, so a stray control character must not
# make the whole feed unparseable.
_INVALID_TEXT = re.compile(
	r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff]"
)


def _clean(value) -> str:
	return _INVALID_TEXT.sub("", str(value or "")).strip()


def feed_context() -> dict:
	"""Everything the RSS template needs, generated from live catalogue data."""
	settings = frappe.get_cached_doc("Shop Settings")
	rows = _rows()
	codes = _item_codes(rows)
	templates = [row.item for row in rows if row.has_variants and row.item]
	variants = catalog.variants_by_template(templates)
	variant_codes = [code for codes in variants.values() for code in codes]
	meta = _item_meta(codes)
	context = {
		"brands": {code: (row.brand or "").strip() for code, row in meta.items()},
		"barcodes": _barcodes(codes),
		"images": images.first_images([row.name for row in rows]),
		"types": _product_types([row.name for row in rows]),
		"variants": variants,
		"variant_attrs": _variant_attributes(variant_codes),
		"prices": pricing.get_prices(codes),
		"qtys": stock.get_stock(codes),
		"meta": meta,
		"allow_out_of_stock": bool(cint(settings.get("allow_out_of_stock"))),
	}
	items = []
	for row in rows:
		items.extend(_product_items(row, settings, context))

	store = _clean(settings.get("store_name") or "reloop")
	return {
		"feed": {
			"title": f"{store} product feed",
			"link": f"{SITE_BASE}/",
			"description": f"New and preloved products from {store}.",
		},
		"items": items,
		"shipping": _shipping(settings),
		"google_product_category": (settings.get("meta_google_product_category") or "").strip(),
	}


def _rows() -> list:
	"""Published products with the fields every feed item needs."""
	return frappe.get_all(
		"Shop Product",
		filters={"published": 1},
		fields=[
			"name",
			"slug",
			"product_name",
			"short_description",
			"description",
			"compare_at_price",
			"condition",
			"item",
			"has_variants",
		],
		order_by="slug asc",
	)


def _item_codes(rows: list) -> list[str]:
	"""Every Item code that can appear in the feed, for one brand lookup."""
	codes = [row.item for row in rows if row.item]
	templates = [row.item for row in rows if row.has_variants and row.item]
	for codes_for_template in catalog.variants_by_template(templates).values():
		codes.extend(codes_for_template)
	return list(dict.fromkeys(codes))


def _barcodes(codes: list[str]) -> dict[str, list[str]]:
	"""All barcodes per item, so the GTIN check can try each one."""
	if not codes:
		return {}
	rows = frappe.get_all(
		"Item Barcode",
		filters={"parent": ["in", codes]},
		fields=["parent", "barcode"],
		order_by="parent, idx",
	)
	out: dict[str, list[str]] = {}
	for row in rows:
		if row.barcode:
			out.setdefault(row.parent, []).append(row.barcode)
	return out


def _item_meta(codes: list[str]) -> dict:
	"""The Item fields the feed needs, in one query instead of one per row."""
	if not codes:
		return {}
	rows = frappe.get_all(
		"Item",
		filters={"name": ["in", codes]},
		fields=["name", "brand", "is_stock_item", "disabled", "image"],
	)
	return {row.name: row for row in rows}


def _variant_attributes(codes: list[str]) -> dict[str, dict]:
	"""Raw variant attribute names and values, keyed by item code."""
	if not codes:
		return {}
	rows = frappe.get_all(
		"Item Variant Attribute",
		filters={"parent": ["in", codes]},
		fields=["parent", "attribute", "attribute_value"],
		order_by="parent, idx",
	)
	out: dict[str, dict] = {}
	for row in rows:
		out.setdefault(row.parent, {})[row.attribute] = row.attribute_value
	return out


def _product_types(product_names: list[str]) -> dict[str, str]:
	"""The highest-ranked published collection title per product, as ``product_type``.

	Merchant Center's ``google_product_category`` is a fixed taxonomy; a single
	shop-wide value is at best a fallback. The collection is the shop's own
	vocabulary ("Shoes", "Bags") and is a useful free-text product type even
	when the taxonomy category is unset.
	"""
	if not product_names:
		return {}
	rows = frappe.get_all(
		"Shop Product Collection",
		filters={"parent": ["in", product_names]},
		fields=["parent", "collection"],
		order_by="parent, idx",
	)
	if not rows:
		return {}
	collections = frappe.get_all(
		"Shop Collection",
		filters={"name": ["in", list({row.collection for row in rows})], "published": 1},
		fields=["name", "title", "ranking"],
	)
	titles = {row.name: row.title for row in collections if row.title}
	ranks = {row.name: (row.ranking or 0) for row in collections}
	best: dict[str, tuple[int, str]] = {}
	for row in rows:
		title = titles.get(row.collection)
		if not title:
			continue
		rank = ranks.get(row.collection, 0)
		if row.parent not in best or rank > best[row.parent][0]:
			best[row.parent] = (rank, title)
	return {parent: title for parent, (_, title) in best.items()}


def _product_items(row, settings, context: dict) -> list[dict]:
	"""One product, expanded into the feed rows Merchant Center should see."""
	product_image = context["images"].get(row.name)
	image_url = image_link(product_image) if product_image else ""
	if not image_url:
		return []

	base_title = _clean(row.product_name or row.slug or row.name)
	description = _plain_text(
		row.description or row.short_description or base_title
	)[:DESCRIPTION_LIMIT]
	link = f"{SITE_BASE}/product/{row.slug}"
	condition = _condition(row.condition)
	base_brand = _clean(context["brands"].get(row.item) or "")
	product_type = _clean(context["types"].get(row.name) or "")

	if not row.has_variants:
		item = context["meta"].get(row.item)
		if not item or item.disabled:
			return []
		rate = flt((context["prices"].get(row.item) or {}).get("rate"))
		if rate <= 0:
			return []
		return [
			_make_item(
				settings=settings,
				id=_feed_id(row.item),
				title=base_title,
				description=description,
				link=link,
				image_url=image_url,
				rate=rate,
				compare_at=row.compare_at_price,
				in_stock=_in_stock(row.item, item, context),
				condition=condition,
				brand=base_brand,
				product_type=product_type,
				gtin=_gtin(row.item, context["barcodes"]),
			)
		]

	group_id = _feed_id(row.item)
	items = []
	for code in context["variants"].get(row.item) or []:
		item = context["meta"].get(code)
		if not item or item.disabled:
			continue
		rate = flt((context["prices"].get(code) or {}).get("rate"))
		if rate <= 0:
			continue
		attrs = _variant_attrs(context["variant_attrs"].get(code) or {})
		variant_image = image_link(item.image) if item.image else image_url
		items.append(
			_make_item(
				settings=settings,
				id=_feed_id(code),
				title=_variant_title(base_title, attrs),
				description=description,
				link=link,
				image_url=variant_image,
				rate=rate,
				compare_at=row.compare_at_price,
				in_stock=_in_stock(code, item, context),
				condition=condition,
				brand=context["brands"].get(code) or base_brand,
				item_group_id=group_id,
				attrs=attrs,
				product_type=product_type,
				gtin=_gtin(code, context["barcodes"]),
			)
		)
	return items


def _in_stock(code: str, item, context: dict) -> bool:
	"""Whether this item can be bought, matching the storefront's rule."""
	if context["allow_out_of_stock"] or not item.is_stock_item:
		return True
	return context["qtys"].get(code, 0) > 0


def _make_item(
	*,
	settings,
	id: str,
	title: str,
	description: str,
	link: str,
	image_url: str,
	rate: float,
	compare_at,
	in_stock,
	condition: str,
	brand: str,
	item_group_id: str | None = None,
	attrs: dict | None = None,
	product_type: str = "",
	gtin: str | None = None,
) -> dict:
	"""One ``<item>`` as plain data, ready to be XML-escaped by the template."""
	currency = settings.get("currency") or "PKR"
	compare_at = flt(compare_at)
	data = {
		"id": _feed_id(id),
		"title": _fit(title, TITLE_LIMIT),
		"description": _clean(description),
		"link": link,
		"image_link": image_url,
		"price": _money(compare_at if compare_at > rate else rate, currency),
		"availability": "in_stock" if in_stock else "out_of_stock",
		"condition": condition,
	}
	if compare_at > rate:
		data["sale_price"] = _money(rate, currency)
	brand = _clean(brand)
	if brand:
		data["brand"] = brand
	if item_group_id:
		data["item_group_id"] = _feed_id(item_group_id)
	if gtin:
		data["gtin"] = gtin
	else:
		# No MPN is stored either, so this is a genuinely unidentified item. The
		# flag is what stops Google rejecting it for a missing GTIN.
		data["identifier_exists"] = "no"
	product_type = _clean(product_type)
	if product_type:
		data["product_type"] = product_type
	if returns := _returns(settings, condition):
		data["returns"] = returns
	data.update(attrs or {})
	return data


def _variant_attrs(attributes: dict) -> dict:
	"""Map ERPNext variant attributes onto Merchant Center's field names."""
	attrs = {}
	for name, value in attributes.items():
		field = VARIANT_FIELDS.get(str(name or "").strip().lower())
		value = _clean(value)
		if field and value and field not in attrs:
			attrs[field] = value[:100]
	return attrs


def _variant_title(base: str, attrs: dict) -> str:
	"""The product name with the variant spelled out.

	Google shows one title per item, and variants of one product otherwise look
	identical in the feed. The size and colour are what distinguish them; the
	product name is trimmed rather than the other way round.
	"""
	parts = []
	if attrs.get("size"):
		parts.append(f"Size {attrs['size']}")
	if attrs.get("color"):
		parts.append(attrs["color"])
	suffix = f" ({' / '.join(parts)})" if parts else ""
	return _fit(base, TITLE_LIMIT, suffix)


def _fit(text: str, limit: int, suffix: str = "") -> str:
	"""Trim the text, never the suffix, so the variant stays identifiable."""
	text = _clean(text)
	if len(text) + len(suffix) <= limit:
		return text + suffix
	room = max(limit - len(suffix), 0)
	return f"{text[:room].rstrip()}{suffix}"[:limit]


def _feed_id(value: str) -> str:
	"""A stable Merchant Center id, inside Google's 50-character limit.

	Long item codes are hashed deterministically rather than truncated: two
	variants of one product can share a long prefix, and a truncated id would
	collide exactly where the suffix differs.
	"""
	text = str(value or "").strip()
	if not text:
		return ""
	if len(text) <= ID_LIMIT:
		return text
	return "g-" + hashlib.sha1(text.encode()).hexdigest()[: ID_LIMIT - 2]


def _gtin(code: str, barcodes: dict[str, list[str]]) -> str | None:
	"""The first barcode on the item that is a real GTIN, or None."""
	for barcode in barcodes.get(code, []):
		if valid := valid_gtin(barcode):
			return valid
	return None


def valid_gtin(value: str | None) -> str | None:
	"""A barcode only becomes a GTIN when its GS1 check digit is correct.

	Google validates the check digit and rejects the item's identifier when it
	fails. A shop-internal barcode typed into the same field must therefore not
	be advertised as a GTIN.
	"""
	digits = re.sub(r"\D", "", str(value or ""))
	if len(digits) not in GTIN_LENGTHS:
		return None
	total = sum(int(char) * (3 if index % 2 == 0 else 1) for index, char in enumerate(reversed(digits[:-1])))
	return digits if (10 - total % 10) % 10 == int(digits[-1]) else None


def _condition(value) -> str:
	"""The admin's free text to Merchant Center's condition enum."""
	text = re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()
	if not text:
		return "new"
	# Checked first: "renewed" contains "new".
	if any(token in text for token in ("refurb", "renew", "open box", "openbox")):
		return "refurbished"
	if "new" in text:
		return "new"
	return "used"


def _plain_text(value: str) -> str:
	"""The storefront's rich HTML copy as the plain text feeds expect.

	Merchant Center renders descriptions literally, so paragraph tags would
	appear in the listing. Paragraph and list breaks survive as newlines.
	"""
	text = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
	text = re.sub(r"</(p|div|li|tr|h[1-6])\s*>", "\n", text, flags=re.I)
	text = re.sub(r"<(p|div|ul|ol|tr|h[1-6])\b[^>]*>", "\n", text, flags=re.I)
	text = re.sub(r"<li[^>]*>", "- ", text, flags=re.I)
	text = re.sub(r"<[^>]+>", "", text)
	text = unescape(text)
	text = re.sub(r"[ \t\u00a0]+", " ", text)
	text = re.sub(r" *\n *", "\n", text)
	text = re.sub(r"\n{3,}", "\n\n", text)
	return text.strip()


def _shipping(settings) -> dict | None:
	"""The shipping rule the storefront actually applies, for every item.

	``shipping_charge`` only charges when a shipping account is configured;
	without one the cart is free, so the feed says free too. The free-shipping
	threshold is an order-total rule and is not represented here -- Google's
	per-item shipping has no minimum-order condition, and applying it per item
	would understate the charge on a mixed basket.
	"""
	country = _country_code(settings.get("address_country"))
	if not country:
		return None
	rate = flt(settings.get("flat_shipping_rate")) if settings.get("shipping_account") else 0.0
	return {
		"country": country,
		"service": "Standard",
		"price": _money(rate, settings.get("currency") or "PKR"),
	}


RETURN_CONDITIONS = {
	"new": "NEW",
	"used": "USED",
	"refurbished": "LIKE_NEW",
}


def _returns(settings, condition: str) -> dict | None:
	"""Offer-level return policy, so it travels with the product.

	The shop's returns flow accepts a return or replacement for 14 days after
	shipping (``shop.storefront.returns``), which is the policy the feed states
	when the newer ``return_window_days`` setting has not been filled in. No
	destination country means no block: Merchant Center requires one, and a
	return promise without a country would be incomplete.
	"""
	country = _country_code(settings.get("address_country"))
	if not country:
		return None
	currency = settings.get("currency") or "PKR"
	return {
		"country": country,
		"item_condition": RETURN_CONDITIONS.get(condition, "USED"),
		"window_days": _return_window_days(settings),
		"window_type": "FINITE_RETURN_WINDOW",
		# The site arranges a pickup for returns, which is a mail/courier return.
		"method": "BY_MAIL",
		"outcome": "REFUND",
		# Free returns: the shop arranges the pickup.
		"shipping_fee": _money(0, currency),
		"shipping_fee_type": "DEDUCTED_FROM_REFUND",
	}


def _return_window_days(settings) -> int:
	"""The configured window, or the one the returns flow actually enforces."""
	try:
		days = int(settings.get("return_window_days") or 0)
	except (TypeError, ValueError):
		days = 0
	return days if days > 0 else RETURN_WINDOW_DAYS


def _country_code(value) -> str | None:
	"""ISO 3166-1 alpha-2, which is what Merchant Center's shipping wants."""
	raw = str(value or "").strip()
	if not raw:
		return None
	if len(raw) == 2 and raw.isalpha():
		return raw.upper()
	code = frappe.db.get_value("Country", raw, "code")
	return code.upper() if code else None


def _money(amount: float, currency: str) -> str:
	return f"{flt(amount):.2f} {currency or 'PKR'}"
