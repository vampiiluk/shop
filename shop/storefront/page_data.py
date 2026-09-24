import frappe
from frappe.utils import cint

from shop.storefront import cart, catalog, checkout, orders, product

PAGE_SIZE = 24


@frappe.whitelist(allow_guest=True)
def home() -> dict:
	return {
		"store": store_details(),
		"collections": catalog.get_collections(),
		"featured_products": catalog.get_products(limit=8)["products"],
	}


@frappe.whitelist(allow_guest=True)
def listing() -> dict:
	form = frappe.form_dict
	page = max(cint(form.get("page")) or 1, 1)
	price_min, price_max = parse_price_bucket(form.get("price"))
	collections = catalog.get_collections()
	result = catalog.get_products(
		collection=form.get("collection"),
		search=form.get("search"),
		sort=form.get("sort") or "ranking",
		start=(page - 1) * PAGE_SIZE,
		limit=PAGE_SIZE,
		price_min=price_min,
		price_max=price_max,
		in_stock=form.get("stock") == "in",
		size=form.get("size"),
		color=form.get("color"),
		with_facets=True,
	)
	applied = applied_filters(form)
	return {
		"store": store_details(),
		"collections": collections,
		"filters": listing_filters(form, collections, facets=result["facets"]),
		"filters_applied": "true" if applied else None,
		"filter_count": str(len(applied)) if applied else None,
		"search": form.get("search") or "",
		"search_label": f'Results for "{form.get("search")}"' if form.get("search") else None,
		"no_results": None if result["products"] else "true",
		"page": page,
		"has_more": page * PAGE_SIZE < result["total"],
		**result,
	}


FILTER_PARAMS = ("collection", "price", "stock", "sort", "size", "color")
# Query parameters a filter link carries over; `collection` only applies to the
# /products listing, since a collection page keeps its slug in the path.
CARRY_PARAMS = ("collection", "search", "sort", "price", "stock", "size", "color")
# Facet filters are scoped to the category they were offered in, so they reset
# when the shopper moves to another collection.
SCOPED_PARAMS = ("size", "color")


def applied_filters(form) -> list[str]:
	"""Which filters the shopper actually set, so the listing can say so when they are hidden."""
	return [key for key in FILTER_PARAMS if form.get(key)]


PRICE_BUCKETS = [
	("0-500", "Under {0}", (None, 500)),
	("500-1000", "{0} to {1}", (500, 1000)),
	("1000-2000", "{0} to {1}", (1000, 2000)),
	("2000-", "Over {0}", (2000, None)),
]

SORT_OPTIONS = [
	("ranking", "Featured"),
	("newest", "Newest"),
	("name", "Name"),
	("price_asc", "Price, low to high"),
	("price_desc", "Price, high to low"),
]


def parse_price_bucket(bucket: str | None):
	for key, _label, (low, high) in PRICE_BUCKETS:
		if bucket == key:
			return low, high
	return None, None


def listing_filters(
	form,
	collections,
	path: str = "/products",
	current_collection: str | None = None,
	facets: dict | None = None,
) -> list[dict]:
	"""Filter groups for the listing, rendered identically on /products and on
	any /collection/<slug> page — ``path`` is what every chip links back to.

	Size and Colour groups are built from ``facets`` (the values actually in
	stock in this category) and simply are not built when there are none, while
	Price, Availability and Sort are always there."""
	from urllib.parse import urlencode

	from frappe.utils import fmt_money

	collection_in_view = current_collection if current_collection is not None else (form.get("collection") or None)

	def option(label, param, value):
		current = form.get(param)
		active = (current or "") == (value or "")
		return {
			"label": label,
			"url": filter_url(form, {param: value}, path),
			"active": "true" if active else "false",
		}

	def collection_option(label, slug):
		"""Collection links keep the shopper on the route they are browsing."""
		active = collection_in_view == slug
		if path != "/products":
			url = "/products" if slug is None else f"/collection/{slug}"
			keep = {key: form.get(key) for key in ("search", "sort", "price", "stock") if form.get(key)}
			return {
				"label": label,
				"url": f"{url}?{urlencode(keep)}" if keep else url,
				"active": "true" if active else "false",
			}
		changes = {"collection": slug}
		if slug != collection_in_view:
			changes.update({key: None for key in SCOPED_PARAMS})
		return {
			"label": label,
			"url": filter_url(form, changes, path),
			"active": "true" if active else "false",
		}

	currency = frappe.get_cached_doc("Shop Settings").currency
	money = lambda amount: fmt_money(amount, currency=currency, precision=0)
	groups = [
		{
			"label": "Collection",
			"options": [
				collection_option("All", None),
				*[collection_option(row.title, row.slug) for row in collections],
			],
		},
	]
	for facet in ("size", "color"):
		found = (facets or {}).get(facet)
		attribute = found["attribute"] if found else facet.title()
		values = list((found or {}).get("values") or [])
		applied_value = form.get(facet)
		if applied_value and applied_value not in values:
			# A value the category does not stock — set by hand, or left over
			# from another collection — still gets its chip, active, so what
			# the shopper is filtering by stays visible and clearable.
			values.append(applied_value)
		if not values:
			continue  # nothing of this kind in the category: no filter for it
		groups.append(
			{
				"label": attribute,
				"options": [
					option(f"Any {attribute.lower()}", facet, None),
					*[option(value, facet, value) for value in values],
				],
			}
		)
	groups.extend(
		[
			{
				"label": "Price",
				"options": [
					option("Any price", "price", None),
					*[
						option(label.format(money(low or high), money(high or low)), "price", key)
						for key, label, (low, high) in PRICE_BUCKETS
					],
				],
			},
			{
				"label": "Availability",
				"options": [option("All", "stock", None), option("In stock", "stock", "in")],
			},
			{
				"label": "Sort",
				"options": [option(label, "sort", None if key == "ranking" else key) for key, label in SORT_OPTIONS],
			},
		]
	)
	return groups


def filter_url(form, changes: dict, path: str = "/products") -> str:
	from urllib.parse import urlencode

	params = {
		key: form.get(key)
		for key in CARRY_PARAMS
		if (key != "collection" or path == "/products") and form.get(key)
	}
	for key, value in changes.items():
		if value:
			params[key] = value
		else:
			params.pop(key, None)
	query = urlencode(params)
	return f"{path}?{query}" if query else path


@frappe.whitelist(allow_guest=True)
def product_page() -> dict:
	detail = product.get_product(frappe.form_dict.slug)
	detail["image"] = detail["images"][0]["image"] if detail["images"] else None
	detail["buy_item_code"] = detail.get("default_item_code") or detail["item"]
	detail["description_text"] = frappe.utils.strip_html(detail.get("description") or "")
	detail["attribute_options"] = [
		{
			"attribute": option["attribute"],
			"values": [{"attribute": option["attribute"], "value": value} for value in option["values"]],
		}
		for option in detail.get("attributes", [])
	]
	detail["show_fabric_band"] = (
		"true" if any(c.get("slug") == "apparel" for c in detail.get("collections") or []) else None
	)
	from shop.storefront import reviews

	return {
		"store": store_details(),
		"product": detail,
		"related_products": related_products(detail),
		"reviews": reviews.get_reviews(detail["name"], limit=6),
	}


def related_products(detail: dict) -> list:
	collections = detail.get("collections") or []
	if collections:
		result = catalog.get_products(collection=collections[0]["slug"], limit=5)["products"]
	else:
		result = catalog.get_products(limit=5)["products"]
	return [product for product in result if product.slug != detail["slug"]][:4]


@frappe.whitelist(allow_guest=True)
def collection_page() -> dict:
	form = frappe.form_dict
	slug = form.slug
	collection = frappe.db.get_value(
		"Shop Collection",
		{"slug": slug, "published": 1},
		["title", "slug", "description", "image"],
		as_dict=True,
	)
	if not collection:
		frappe.throw(frappe._("Collection not found"), frappe.DoesNotExistError)
	page = max(cint(form.get("page")) or 1, 1)
	price_min, price_max = parse_price_bucket(form.get("price"))
	collections = catalog.get_collections()
	path = f"/collection/{slug}"
	result = catalog.get_products(
		collection=slug,
		search=form.get("search"),
		sort=form.get("sort") or "ranking",
		start=(page - 1) * PAGE_SIZE,
		limit=PAGE_SIZE,
		price_min=price_min,
		price_max=price_max,
		in_stock=form.get("stock") == "in",
		size=form.get("size"),
		color=form.get("color"),
		with_facets=True,
	)
	applied = applied_filters(form)
	return {
		"store": store_details(),
		"collection": collection,
		# Filters like the All products page, but every chip links back to
		# /collection/<slug> and the Size/Colour groups only exist when this
		# category actually has those variants.
		"filters": listing_filters(
			form,
			collections,
			path=path,
			current_collection=slug,
			facets=result["facets"],
		),
		"filters_applied": "true" if applied else None,
		"filter_count": str(len(applied)) if applied else None,
		"clear_url": path,
		"search": form.get("search") or "",
		"no_results": None if result["products"] else "true",
		"page": page,
		"has_more": page * PAGE_SIZE < result["total"],
		**result,
	}


@frappe.whitelist(allow_guest=True)
def basic() -> dict:
	return {"store": store_details()}


@frappe.whitelist(allow_guest=True)
def cart_page() -> dict:
	return {"store": store_details(), "cart": cart.get_cart()}


@frappe.whitelist(allow_guest=True)
def checkout_page() -> dict:
	store = store_details()
	result = checkout.get_checkout_summary()
	result["store"] = store
	# Expose store fields at the top level so Builder page_data_script can access them.
	for key in ("address_cities", "address_provinces", "address_country", "landmark_required", "province_city_map", "cod_allowed_cities", "advance_instructions"):
		result[key] = store.get(key)
	return result


@frappe.whitelist(allow_guest=True)
def order_confirmation() -> dict:
	form = frappe.form_dict
	return {
		"store": store_details(),
		"order": orders.get_order_summary(form.order_id, form.get("token")),
	}


@frappe.whitelist()
def account_orders() -> dict:
	return {"store": store_details(), "orders": orders.get_orders()}


def store_details() -> dict:
	settings = frappe.get_cached_doc("Shop Settings")
	signed_in = frappe.session.user not in ("Guest", None)
	result = {
		"name": settings.store_name,
		"logo": settings.store_logo,
		"currency": settings.currency,
		"enable_cod": settings.enable_cod,
		"account_label": frappe._("Account") if signed_in else frappe._("Sign in"),
		"account_url": "/account/orders" if signed_in else "/login?redirect-to=/account/orders",
		"fp_public_key": settings.fingerprint_public_key or "",
		"fp_region": settings.fingerprint_region or "ap",
		"fingerprint_provider": settings.fingerprint_provider or "thumbmarkjs",
		"landmark_required": settings.landmark_required,
	}
	from shop.integrations.fraud import canonical_cities, canonical_provinces

	result["address_cities"] = [{"name": c.title()} for c in canonical_cities()]
	result["address_provinces"] = [{"name": p.title()} for p in canonical_provinces()]
	if settings.address_country:
		result["address_country"] = [{"name": settings.address_country}]
	# Build province→cities mapping for the checkout cascading dropdown
	province_map = {}
	province_table = getattr(settings, "province_table", None)
	if province_table:
		for row in province_table:
			prov = (row.province_name or "").strip()
			if prov:
				cities = [c.strip().title() for c in (row.cities or "").split(",") if c.strip()]
				province_map[prov] = cities
	result["province_city_map"] = province_map
	result["cod_allowed_cities"] = [
		c.strip().lower()
		for c in (getattr(settings, "cod_allowed_cities", None) or "").split(",")
		if c.strip()
	]
	result["advance_instructions"] = (settings.advance_payment_instructions or "").strip() or None
	return result
