"""Orders placed by hand.

A shop takes orders over the phone, on WhatsApp and at the counter, and
those orders have to land in the same place as the ones the site takes:
the same Sales Order, the same customer, the same fulfilment, the same
invoice and the same receipt.

So this is the storefront's own order machinery, driven by the desk
instead of by a checkout form. The one thing it deliberately leaves out is
the automated fraud block: that control exists because an anonymous
checkout form offers no proof of who is filling it in, and a merchant
placing an order at the counter is proof of exactly that.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, nowdate, validate_email_address

from shop.api import only_managers
from shop.api.products import display_names, sellable_codes
from shop.storefront import cart as cart_module
from shop.storefront import checkout, pricing, stock


@frappe.whitelist()
def form_options() -> dict:
	"""What the desk needs to draw the form: the settings behind it."""
	only_managers()
	settings = frappe.get_cached_doc("Shop Settings")
	from shop.integrations.fraud import canonical_cities, canonical_provinces

	methods = []
	if cint(settings.enable_cod):
		methods.append({"value": "cod", "label": _("Cash on Delivery")})
	if cint(settings.enable_advance_payment):
		methods.append({"value": "advance", "label": _("Advance Payment")})
	if cint(settings.enable_pickup):
		methods.append({"value": "pickup", "label": _("Store Pickup")})

	return {
		"company": settings.company,
		"price_list": settings.price_list,
		"warehouse": settings.default_warehouse,
		"countries": frappe.get_all("Country", pluck="name", order_by="name"),
		"default_country": settings.address_country or frappe.db.get_default("country"),
		"cities": [city.title() for city in canonical_cities()],
		"provinces": [province.title() for province in canonical_provinces()],
		"cod_cities": checkout.cod_cities(settings),
		"landmark_required": cint(settings.landmark_required),
		"payment_methods": methods,
	}


@frappe.whitelist()
def catalogue(search: str = "", limit: int = 20) -> list[dict]:
	"""The products that can be put on a hand-placed order.

	Each product carries the items it can be sold as - one for a plain
	product, one per size or colour for a product that varies - with the
	price and the stock of each, so the desk does not have to ask for a
	rate it cannot check.
	"""
	only_managers()
	or_filters = None
	if search:
		term = f"%{search.strip()}%"
		or_filters = [["product_name", "like", term], ["slug", "like", term], ["item", "like", term]]
	products = frappe.get_all(
		"Shop Product",
		or_filters=or_filters,
		fields=["name", "product_name", "item", "has_variants"],
		order_by="product_name asc",
		limit=min(cint(limit) or 20, 50),
	)
	for product in products:
		codes = sellable_codes(product.item, product.has_variants)
		prices = pricing.get_prices(codes)
		names = display_names(codes)
		stock_by_code = stock.get_stock(codes)
		product["options"] = [
			{
				"item_code": code,
				"label": names.get(code) or code,
				"rate": prices.get(code, {}).get("rate") or 0,
				"formatted_rate": prices.get(code, {}).get("formatted") or "",
				"stock": stock_by_code.get(code, 0),
			}
			for code in codes
		]
	return products


@frappe.whitelist(methods=["POST"])
def create(payload: dict) -> dict:
	"""Place an order on a customer's behalf.

	Returns the order's name, so the desk can open it.
	"""
	only_managers()
	settings = frappe.get_cached_doc("Shop Settings")

	customer = _customer(payload.get("customer") or {})
	address = _address(payload.get("address") or {})
	lines = _lines(payload.get("items") or [])
	payment_method = (payload.get("payment_method") or "cod").strip()
	notes = (payload.get("notes") or "").strip()
	send_email = bool(payload.get("send_email"))

	_validate(customer, address, lines, payment_method, settings)

	with checkout.elevated():
		party = checkout.get_or_create_customer(customer)
		shipping_address = checkout.create_address(party, customer, address)
		order = _create_sales_order(
			settings, party, shipping_address, customer, address, lines, payment_method, notes
		)
		# A cart carries the guest's secret, which is what lets a customer
		# who is not signed in open the order from the receipt. A hand-
		# placed order needs one too, or the link in the receipt is dead.
		cart = _create_cart(order, lines)
		confirmation_url = f"/order-confirmation/{order.name}?token={cart.token}"

		from shop.api.orders import auto_billing_enabled, create_sales_invoice_for_order

		if auto_billing_enabled():
			try:
				create_sales_invoice_for_order(order.name)
			except Exception:
				frappe.log_error(
					title="Manual order auto-invoice failed",
					reference_doctype="Sales Order",
					reference_name=order.name,
				)

		if send_email:
			checkout.queue_confirmation_email(order, customer["email"], confirmation_url)

	return {"order": order.name, "email_sent": send_email}


# --- the pieces of an order ------------------------------------------------


def _customer(payload: dict) -> dict:
	full_name = (payload.get("full_name") or "").strip()
	email = (payload.get("email") or "").strip()
	phone = (payload.get("phone") or "").strip()
	if not full_name:
		frappe.throw(_("The customer's name is required"))
	if not email:
		frappe.throw(_("The customer's email is required"))
	validate_email_address(email, throw=True)
	if not phone:
		frappe.throw(_("The customer's phone number is required"))
	return {"full_name": full_name, "email": email, "phone": phone}


def _address(payload: dict) -> dict:
	address = {
		"address_line1": (payload.get("address_line1") or "").strip(),
		"address_line2": (payload.get("address_line2") or "").strip(),
		"city": (payload.get("city") or "").strip(),
		"state": (payload.get("state") or "").strip(),
		"country": (payload.get("country") or "").strip(),
		"pincode": (payload.get("pincode") or "").strip(),
		"landmark": (payload.get("landmark") or "").strip(),
		"alt_phone": (payload.get("alt_phone") or "").strip(),
	}
	if not address["address_line1"]:
		frappe.throw(_("The delivery address is required"))
	if not address["city"]:
		frappe.throw(_("The city is required"))
	if not address["pincode"]:
		frappe.throw(_("The pincode is required"))
	return address


def _lines(payload: list) -> list[dict]:
	lines = []
	for row in payload:
		item_code = (row.get("item_code") or "").strip()
		if not item_code:
			continue
		qty = flt(row.get("qty"))
		if qty <= 0:
			frappe.throw(_("Every line needs a quantity of at least one"))
		lines.append({"item_code": item_code, "qty": qty, "rate": flt(row.get("rate"))})
	if not lines:
		frappe.throw(_("The order needs at least one item"))
	return lines


def _validate(customer, address, lines, payment_method, settings) -> None:
	if payment_method not in ("cod", "advance", "pickup"):
		frappe.throw(_("Choose a payment method"))
	if payment_method == "cod" and not cint(settings.enable_cod):
		frappe.throw(_("Cash on Delivery is not available"))
	if payment_method == "advance" and not cint(settings.enable_advance_payment):
		frappe.throw(_("Advance payment is not available"))
	if payment_method == "pickup" and not cint(settings.enable_pickup):
		frappe.throw(_("Store pickup is not available"))
	if payment_method == "cod":
		allowed = checkout.cod_cities(settings)
		city = (address.get("city") or "").strip().lower()
		if allowed and city not in allowed:
			frappe.throw(
				_("Cash on Delivery is not offered in {0}.").format(address.get("city") or _("this city"))
			)
	if cint(settings.landmark_required) and payment_method != "pickup":
		if not (address.get("landmark") or "").strip():
			frappe.throw(
				_("Nearest landmark is required so delivery riders can find you.")
			)
	for line in lines:
		# The same rule the site applies: a line is only sold if the item
		# is purchasable and there is the stock for it.
		cart_module.validate_purchasable(line["item_code"])
		if cint(settings.allow_out_of_stock):
			continue
		if not frappe.get_cached_value("Item", line["item_code"], "is_stock_item"):
			continue
		available = stock.get_stock([line["item_code"]]).get(line["item_code"], 0)
		if available < line["qty"]:
			frappe.throw(_("Only {0} of {1} left in stock").format(int(available), line["item_code"]))


def _create_sales_order(
	settings, party, shipping_address, customer, address, lines, payment_method, notes
):
	company_currency = frappe.get_cached_value("Company", settings.company, "default_currency")
	order = frappe.get_doc(
		{
			"doctype": "Sales Order",
			"company": settings.company,
			"customer": party,
			"order_type": "Sales",
			"delivery_date": add_days(nowdate(), 3),
			"selling_price_list": settings.price_list,
			"currency": settings.currency or company_currency,
			"conversion_rate": 1,
			"plc_conversion_rate": 1,
			"customer_address": shipping_address.name,
			"shipping_address_name": shipping_address.name,
			"custom_manual_order": 1,
			"custom_order_notes": notes or None,
			"custom_payment_method": payment_method,
			"contact_email": customer["email"],
			"contact_phone": customer["phone"],
			"contact_mobile": customer["phone"],
			"items": [
				{
					"item_code": line["item_code"],
					"qty": line["qty"],
					"rate": line["rate"],
					"warehouse": settings.default_warehouse,
				}
				for line in lines
			],
		}
	)
	checkout.apply_taxes(order, settings)
	if payment_method != "pickup":
		# Pickup hands the order over in person, so there is no courier to
		# charge for.
		checkout.apply_shipping(order, settings, 0)
	order.flags.ignore_permissions = True
	order.insert(ignore_permissions=True)
	order.submit()
	return order


def _create_cart(order, lines):
	"""The cart that carries the guest's secret for the receipt link."""
	cart = frappe.new_doc("Shop Cart")
	cart.status = "Converted"
	cart.sales_order = order.name
	for line in lines:
		cart.append("items", {"item_code": line["item_code"], "qty": line["qty"], "rate": line["rate"]})
	cart.insert(ignore_permissions=True)
	return cart
