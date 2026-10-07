import frappe
from frappe.utils import cint, flt


def get_stock(item_codes: list[str]) -> dict[str, float]:
	if not item_codes:
		return {}
	settings = frappe.get_cached_doc("Shop Settings")
	rows = frappe.get_all(
		"Bin",
		filters={"item_code": ["in", item_codes], "warehouse": settings.default_warehouse},
		fields=["item_code", "actual_qty"],
	)
	qty_map = dict.fromkeys(item_codes, 0.0)
	qty_map.update({row.item_code: row.actual_qty for row in rows})
	return qty_map


def is_in_stock(item_code: str) -> bool:
	settings = frappe.get_cached_doc("Shop Settings")
	if settings.allow_out_of_stock:
		return True
	if not frappe.get_cached_value("Item", item_code, "is_stock_item"):
		return True
	return get_stock([item_code]).get(item_code, 0) > 0


def variants_of(templates: list[str]) -> dict[str, list[str]]:
	"""Child variant item codes, grouped by their template."""
	if not templates:
		return {}
	rows = frappe.get_all(
		"Item", filters={"variant_of": ["in", templates]}, fields=["name", "variant_of"]
	)
	grouped: dict[str, list[str]] = {}
	for row in rows:
		grouped.setdefault(row.variant_of, []).append(row.name)
	return grouped


def total_stock_map(codes: list[str]) -> dict[str, float]:
	"""Stock for whole products: a product's own item plus every variant.

	"This product" has to mean every size and colour of it. Summing only the
	template reports a product as sold out while each of its variants is sitting
	on the shelf, which is the same class of mistake as reading one geocoder's
	answer as the truth.
	"""
	if not codes:
		return {}
	all_codes = list(codes)
	by_variant = variants_of(codes)
	extra = [c for group in by_variant.values() for c in group]
	all_codes += extra
	qty = get_stock(list(dict.fromkeys(all_codes)))
	totals = {}
	for code in codes:
		total = flt(qty.get(code, 0))
		for child in by_variant.get(code, []):
			total += flt(qty.get(child, 0))
		totals[code] = total
	return totals


def total_stock(code: str) -> float:
	return total_stock_map([code]).get(code, 0.0)


def low_stock_threshold() -> int:
	settings = frappe.get_cached_doc("Shop Settings")
	return max(cint(settings.low_stock_threshold) or 0, 0)


def availability(code: str, total: float | None = None) -> str:
	"""One of sold_out / limited / in_stock, for the tag above a product name.

	in_stock covers the cases where a stock tag would be wrong rather than
	merely unhelpful: a shop that allows selling past zero, or an item that is
	not stock-managed at all. Neither should ever be labelled "Limited stock",
	because nothing is being counted for them.
	"""
	settings = frappe.get_cached_doc("Shop Settings")
	if settings.allow_out_of_stock:
		return "in_stock"
	if not frappe.get_cached_value("Item", code, "is_stock_item"):
		return "in_stock"
	if total is None:
		total = total_stock(code)
	if total <= 0:
		return "sold_out"
	if 0 < total < low_stock_threshold():
		return "limited"
	return "in_stock"


# The tag text is decided here rather than in the page generator, because the
# builder's visibilityCondition takes a single key and cannot express
# "availability is limited". Two plain strings, each empty or not, is the
# simplest thing the existing machinery can gate on.
SOLD_OUT_TAG = "Sold out"
LIMITED_TAG = "Limited stock"


def stock_tags(code: str, total: float | None = None) -> dict:
	"""The two tag fields the product page and product cards gate on."""
	state = availability(code, total)
	return {
		"sold_out_tag": SOLD_OUT_TAG if state == "sold_out" else "",
		"limited_tag": LIMITED_TAG if state == "limited" else "",
	}
