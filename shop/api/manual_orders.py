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
from shop.storefront import checkout, coupons, pricing, stock


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


@frappe.whitelist()
def check_coupon(code: str, subtotal: float) -> dict:
	"""What a coupon would do to this order, without placing the order.

	The merchant should see the discount before the order exists, and the
	coupon's own rules - expired, used up, the minimum spend - are worth
	saying out loud rather than leaving to a failure at the end.
	"""
	only_managers()

	code = (code or "").strip()
	if not code:
		return {"valid": 0, "message": ""}
	try:
		coupon = coupons.resolve(code)
		discount = coupons.discount_for(coupon, flt(subtotal))
	except Exception as error:
		return {"valid": 0, "message": str(error)}
	return {
		"valid": 1,
		"code": coupon.code,
		"discount": discount,
		"formatted_discount": pricing.format_amount(discount),
		"message": "",
	}


@frappe.whitelist()
def search_customers(search: str, limit: int = 8) -> list[dict]:
	"""The customers the shop already has, found by name, email or phone.

	A merchant taking an order over the phone should not have to retype what
	the shop already knows, and an order typed against a new record when the
	shop already has the customer splits their history in two. So the search
	looks in all three places a merchant would think to look: the name, the
	email, and the number.
	"""
	only_managers()
	term = (search or "").strip()
	if len(term) < 2:
		return []

	names = set(frappe.get_all("Customer", filters={"customer_name": ["like", f"%{term}%"]}, pluck="name"))

	# The email and the phone live on the contact, not on the customer, so
	# they are found there and the customer is looked up from the contact.
	contacts = set()
	for table in ("tabContact Email", "tabContact Phone"):
		column = "email_id" if "Email" in table else "phone"
		contacts.update(
			frappe.db.sql(
				f"select parent from `{table}` where {column} like %s limit 50",  # nosemgrep
				(f"%{term}%",),
				pluck=True,
			)
		)
	if contacts:
		names.update(
			frappe.get_all(
				"Dynamic Link",
				filters={
					"parenttype": "Contact",
					"parent": ["in", list(contacts)],
					"link_doctype": "Customer",
				},
				pluck="link_name",
			)
		)
	if not names:
		return []

	customers = frappe.get_all(
		"Customer",
		filters={"name": ["in", list(names)]},
		fields=["name", "customer_name"],
		limit=min(cint(limit) or 8, 25),
	)
	details = contact_details([row.name for row in customers])
	from shop.api.customers import order_totals

	totals = order_totals([row.name for row in customers])
	found = []
	for row in customers:
		contact = details.get(row.name, {})
		summary = totals.get(row.name, {"orders": 0, "spent": 0.0})
		found.append(
			{
				"name": row.name,
				"customer_name": row.customer_name,
				"email": contact.get("email") or "",
				"phone": contact.get("phone") or "",
				"orders": summary["orders"],
				"formatted_spent": pricing.format_amount(summary["spent"]),
			}
		)
	return found


def contact_details(customers: list[str]) -> dict:
	"""The email and the phone each customer is reached on."""
	if not customers:
		return {}
	links = frappe.get_all(
		"Dynamic Link",
		filters={"link_doctype": "Customer", "link_name": ["in", customers], "parenttype": "Contact"},
		fields=["link_name", "parent"],
	)
	parents = list({link.parent for link in links})
	if not parents:
		return {}
	emails: dict[str, list[str]] = {}
	for row in frappe.get_all("Contact Email", filters={"parent": ["in", parents]}, fields=["parent", "email_id"]):
		emails.setdefault(row.parent, []).append(row.email_id)
	phones: dict[str, list[str]] = {}
	for row in frappe.get_all("Contact Phone", filters={"parent": ["in", parents]}, fields=["parent", "phone"]):
		phones.setdefault(row.parent, []).append(row.phone)

	details: dict[str, dict] = {}
	for link in links:
		entry = details.setdefault(link.link_name, {})
		entry["email"] = entry.get("email") or next(iter(emails.get(link.parent, [])), "")
		entry["phone"] = entry.get("phone") or next(iter(phones.get(link.parent, [])), "")
	return details


@frappe.whitelist()
def customer_addresses(customer: str) -> list[dict]:
	"""The addresses a customer has been delivered to before."""
	only_managers()
	if not customer or not frappe.db.exists("Customer", customer):
		return []
	names = frappe.get_all(
		"Dynamic Link",
		filters={"parenttype": "Address", "link_doctype": "Customer", "link_name": customer},
		pluck="parent",
	)
	if not names:
		return []
	rows = frappe.get_all(
		"Address",
		filters={"name": ["in", names]},
		fields=[
			"name",
			"address_line1",
			"address_line2",
			"city",
			"state",
			"country",
			"pincode",
			"custom_landmark",
			"custom_alt_phone",
		],
		order_by="modified desc",
	)
	return [
		{
			"name": row.name,
			"address_line1": row.address_line1 or "",
			"address_line2": row.address_line2 or "",
			"city": row.city or "",
			"state": row.state or "",
			"country": row.country or "",
			"pincode": row.pincode or "",
			"landmark": row.get("custom_landmark") or "",
			"alt_phone": row.get("custom_alt_phone") or "",
		}
		for row in rows
	]


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
	coupon_code = (payload.get("coupon_code") or "").strip()

	_validate(customer, address, lines, payment_method, settings)

	# The coupon is resolved before the order is built, so a bad code is
	# refused before anything is written.
	coupon, discount = _coupon(coupon_code, lines)

	with checkout.elevated():
		party = checkout.get_or_create_customer(customer)
		shipping_address = checkout.create_address(party, customer, address)
		order = _create_sales_order(
			settings,
			party,
			shipping_address,
			customer,
			address,
			lines,
			payment_method,
			notes,
			coupon,
			discount,
		)
		if coupon:
			# Count the redemption against the cap, the way the checkout
			# does. ERPNext counts a redemption only for an order that
			# carries the coupon itself, and this order carries the
			# discount instead, so this is the count. If the cap has been
			# reached in the meantime this throws, and the order goes with
			# it.
			coupons.redeem(coupon.name)
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


def _coupon(code: str, lines: list[dict]):
	"""The coupon on this order and the discount it gives.

	The same rules the checkout applies, including the minimum spend, so a
	code that would be refused at checkout is refused here too.
	"""
	if not code:
		return None, 0.0
	subtotal = sum(flt(line["rate"]) * flt(line["qty"]) for line in lines)
	coupon = coupons.resolve(code)
	discount = coupons.discount_for(coupon, subtotal)
	return coupon, discount


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
	settings,
	party,
	shipping_address,
	customer,
	address,
	lines,
	payment_method,
	notes,
	coupon=None,
	discount: float = 0.0,
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
	if coupon:
		# The discount is set by hand, so the order is told to leave the
		# pricing rules alone. Every rule this shop has is a coupon rule,
		# and a coupon rule that finds no coupon on the transaction takes
		# the discount away again as it is applied - which is why a coupon
		# that resolves, is priced and is redeemed can still leave the
		# order at full price.
		#
		# Left to itself ERPNext would price the discount off the total
		# including shipping and tax rather than the items, and would
		# refuse a flat coupon on a small order outright. The figure here
		# is the one the merchant was shown before they pressed the
		# button, and the one the shop's own pricing rules arrive at.
		order.ignore_pricing_rule = 1
		order.apply_discount_on = "Grand Total"
		order.discount_amount = discount
		# The coupon is written down on the order, so the desk can show
		# it and the books can be checked against it later.
		order.custom_coupon_code = coupon.code
	checkout.apply_taxes(order, settings)
	if payment_method != "pickup":
		# Pickup hands the order over in person, so there is no courier to
		# charge for.
		checkout.apply_shipping(order, settings, discount)
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
