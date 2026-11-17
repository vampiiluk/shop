"""Give the products already in the catalogue a brand.

``Item.brand`` is the field the storefront, the product schema and any future
brand page read. It was empty on every item, so a Nike shoe and an unbranded
clog were indistinguishable to Google and a brand facet had nothing to group.

The brand is matched from the product name, which is how the catalogue has
always carried it: there was no separate field to read. Names are only trusted
at the start of the string and only against a curated list, because a loose
substring match is how "Daily Essential Clogs" becomes a Clarks shoe. Anything
not matched is left blank on purpose -- an absent brand is true, a guessed one
is not.

The patch is idempotent and never overwrites a brand that is already set, so a
correction made by hand before or after it runs is preserved.
"""

import frappe

# (Brand record, name prefixes). Prefixes are compared case-folded at the start
# of the product name. A prefix is accepted when what follows is not a letter or
# digit, so "Nike" matches "Nike ARMY" but not "Niketo", and "Clark" does not
# swallow "Clarks" -- those two are listed separately.
BRANDS = (
	("Adidas", ("adidas",)),
	("Allbirds", ("allbirds",)),
	("ASICS", ("asics",)),
	("Bubba", ("bubba",)),
	("Clarks", ("clark", "clarks")),
	("Clove", ("clove",)),
	("CMP", ("cmp",)),
	("Cole Haan", ("cole haan",)),
	("Columbia", ("columbia",)),
	("Contigo", ("contigo",)),
	("ECCO", ("ecco",)),
	("Funko", ("funko",)),
	("Hape", ("hape",)),
	("Herschel", ("herschel",)),
	("HOKA", ("hoka",)),
	("Hydro Flask", ("hydro flask",)),
	("Kindi Kids", ("kindi kids",)),
	("Kipling", ("kipling",)),
	("L.O.L. Surprise", ("l.o.l. surprise",)),
	("Lancaster", ("lancaster",)),
	("LeapFrog", ("leap frog", "leapfrog")),
	("Li-Ning", ("li-ning", "li ning")),
	("Lock & Lock", ("lock & lock",)),
	("Longchamp", ("longchamp",)),
	("Lorna Jane", ("lorna jane",)),
	("Mandarina Duck", ("mandarina duck",)),
	("Mizuno", ("mizuno",)),
	("Nerf", ("nerf",)),
	("Nike", ("nike",)),
	("Osprey", ("osprey",)),
	("PicassoTiles", ("picassotiles",)),
	("Quechua", ("quechua",)),
	("Reebok", ("reebok",)),
	("Reserved", ("reserved",)),
	("Skechers", ("skechers",)),
	("Solo New York", ("solo",)),
	("Starbucks", ("starbucks",)),
	("Supreme", ("supreme",)),
	("Swiss Gear", ("swiss gear",)),
	("Targoss", ("targoss",)),
	("The North Face", ("the north face",)),
	("ThermoFlask", ("thermoflask",)),
	("Thermos", ("thermos",)),
	("Tommee Tippee", ("tommee tippee",)),
	("TravisMathew", ("travismathew",)),
	("Vans", ("vans",)),
	("Victoria's Secret", ("victoria's secret", "victoria’s secret")),
	("Zara", ("zara",)),
)


def execute():
	created = 0
	assigned = 0
	for product in frappe.get_all("Shop Product", fields=["item", "product_name"]):
		item = product.item
		if not item or frappe.db.get_value("Item", item, "brand"):
			continue
		name = product.product_name or frappe.db.get_value("Item", item, "item_name") or ""
		brand = match_brand(name)
		if not brand:
			continue
		created += ensure_brand(brand)
		assigned += set_brand(item, brand)

	frappe.db.commit()
	# The graph on the home and listing pages describes the whole catalogue from
	# one cached payload; leaving it in place would serve the pre-backfill version
	# for its full TTL even though the data behind it has changed.
	from shop.storefront import seo

	frappe.cache().delete_value(seo.CATALOG_CACHE_KEY)
	frappe.logger("shop").info(
		f"Brand backfill: {assigned} item(s) branded, {created} Brand record(s) created"
	)


def match_brand(product_name: str) -> str | None:
	"""The curated brand a product name starts with, or None."""
	name = (product_name or "").strip().casefold()
	if not name:
		return None
	for brand, prefixes in BRANDS:
		for prefix in prefixes:
			if not name.startswith(prefix):
				continue
			rest = name[len(prefix) :]
			if not rest or not (rest[0].isalnum() or rest[0] in "'’"):
				return brand
	return None


def ensure_brand(brand: str) -> int:
	"""Create the Brand record when it is missing. 1 when created, else 0."""
	for existing in frappe.get_all("Brand", pluck="name"):
		if existing.casefold() == brand.casefold():
			return 0
	frappe.get_doc({"doctype": "Brand", "brand": brand}).insert(ignore_permissions=True)
	return 1


def set_brand(item_code: str, brand: str) -> int:
	"""Write the brand to the template and every variant. Returns rows written."""
	codes = [item_code] + frappe.get_all(
		"Item", filters={"variant_of": item_code}, pluck="name"
	)
	for code in codes:
		frappe.db.set_value("Item", code, "brand", brand, update_modified=False)
	return len(codes)
