import frappe
from frappe import _
from frappe.utils import cint, flt

from shop.storefront import cart as cart_module
from shop.storefront import pricing


STATUS_LABELS = {
	"To Deliver and Bill": "Processing",
	"To Deliver": "Processing",
	"To Bill": "Shipped",
	"Completed": "Delivered",
	"On Hold": "On hold",
}


@frappe.whitelist()
def get_orders(start: int = 0, limit: int = 20) -> list[dict]:
	customers = session_customers()
	if not customers:
		return []
	orders = frappe.get_all(
		"Sales Order",
		filters={"customer": ["in", customers], "docstatus": 1},
		fields=["name", "transaction_date", "status", "grand_total", "currency", "custom_payment_method"],
		order_by="creation desc",
		start=cint(start),
		limit=min(cint(limit) or 20, 50),
	)
	from shop.api.orders import payment_status_label, payments_received

	received_map = payments_received([order.name for order in orders])
	for order in orders:
		order.formatted_total = pricing.format_amount(order.grand_total)
		order.display_status = STATUS_LABELS.get(order.status, order.status)
		order.formatted_date = frappe.utils.formatdate(order.transaction_date, "d MMM yyyy")
		order.url = f"/order-confirmation/{order.name}"
		order.payment_status = payment_status_label(
			order.custom_payment_method, received_map.get(order.name), order.grand_total
		)
	return orders


@frappe.whitelist()
def get_order(name: str) -> dict:
	order = frappe.get_doc("Sales Order", name)
	if order.customer not in session_customers():
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	return order_summary(order)


@frappe.whitelist(allow_guest=True)
def get_order_summary(name: str, token: str | None = None) -> dict:
	if not can_view(name, token):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	return order_summary(frappe.get_doc("Sales Order", name))


def can_view(name: str, token: str | None) -> bool:
	"""The cart token doubles as the guest secret; the signed-in owner needs no token."""
	if token and frappe.db.exists("Shop Cart", {"token": token, "sales_order": name}):
		return True
	customers = session_customers()
	return bool(customers) and frappe.db.get_value("Sales Order", name, "customer") in customers


def order_summary(order) -> dict:
	from shop.api.orders import payment_status_label, payments_received
	from shop.storefront import returns

	shipment = shipment_summary(order.name)
	method = order.get("custom_payment_method") or "cod"
	# What the customer still owes, straight off the ledger: the confirmation
	# page shows a payment status next to the QR, and that status has to flip
	# to Paid on its own once the transfer is recorded — a checkout screen
	# that keeps calling a settled order unpaid is worse than no status at all.
	payment_status = payment_status_label(method, payments_received([order.name]).get(order.name), order.grand_total)
	return {
		"returns": returns.summary(order.name),
		"name": order.name,
		"status": order.status,
		"display_status": STATUS_LABELS.get(order.status, order.status),
		"progress": order_progress(order, shipment),
		"shipment": shipment,
		"fulfillment_name": shipment.name if shipment else None,
		"awaiting_shipment": None if shipment or method == "pickup" else "true",
		"transaction_date": str(order.transaction_date),
		"total": order.total,
		"formatted_total": pricing.format_amount(order.total),
		"formatted_shipping": shipping_label(order),
		"discount_amount": order.discount_amount or None,
		"formatted_discount": pricing.format_amount(order.discount_amount)
		if order.discount_amount
		else None,
		"grand_total": order.grand_total,
		"formatted_grand_total": pricing.format_amount(order.grand_total),
		"payment_method": method,
		"payment_status": payment_status,
		"advance_payment": advance_payment_info(order),
		"raast": raast_payment_info(order),
		"pickup_location": pickup_location_info(order),
		"taxes": [
			{"description": tax.description, "amount": tax.tax_amount, "formatted_amount": pricing.format_amount(tax.tax_amount)}
			for tax in order.taxes
		],
		"items": [
			{
				"item_code": row.item_code,
				"item_name": row.item_name,
				"qty": cart_module.display_qty(row.qty),
				"rate": row.rate,
				"formatted_rate": pricing.format_amount(row.rate),
				"amount": row.amount,
				"formatted_amount": pricing.format_amount(row.amount),
				"image": row.image,
			}
			for row in order.items
		],
	}


def advance_payment_info(order) -> dict | None:
	"""Advance block for the confirmation page; None unless the customer chose advance."""
	if (order.get("custom_payment_method") or "cod") != "advance":
		return None
	from shop.api.orders import payments_received

	received = payments_received([order.name]).get(order.name) or 0.0
	total = flt(order.grand_total)
	advance = flt(order.custom_advance_amount or 0)
	# What the courier still collects on delivery: everything past the prepayment
	# milestone (the recorded advance, or the promised advance if not yet received).
	courier = max(total - max(received, min(advance, total)), 0.0)
	due_now = max(advance - received, 0.0)
	if received <= 0:
		line = _(
			"Advance due: {0} — pay to the account below and your order ships. The courier collects {1} on delivery."
		).format(pricing.format_amount(due_now), pricing.format_amount(courier))
	else:
		line = _("Advance received: {0} · the courier collects {1} on delivery.").format(
			pricing.format_amount(received), pricing.format_amount(courier)
		)
	return {
		"line": line,
		"advance_amount": advance,
		"formatted_advance_amount": pricing.format_amount(advance),
		"due": due_now,
		"formatted_due": pricing.format_amount(due_now),
		"received": received,
		"formatted_received": pricing.format_amount(received),
		"balance": courier,
		"formatted_balance": pricing.format_amount(courier),
	}


def raast_payment_info(order) -> dict | None:
	"""Raast QR block for the confirmation page; None unless the customer chose it.

	The QR, the copyable account details and the download link all come from
	one encoder so the panel can never show a code that disagrees with the
	account it names.
	"""
	from shop import payments

	return payments.payment_context(order)


def pickup_location_info(order) -> dict | None:
	"""Pickup block for the confirmation page; None unless the customer chose pickup."""
	if (order.get("custom_payment_method") or "cod") != "pickup":
		return None
	from shop.storefront import pickup as pickup_module

	stored = (order.get("custom_pickup_location") or "").strip()
	for row in pickup_module.configured():
		if row["name"].lower() == stored.lower():
			return row
	# The location was renamed or removed after this order: keep the name the
	# customer picked so the tile still identifies the handover point.
	return {
		"name": stored or _("Store pickup"),
		"address": "",
		"latitude": "",
		"longitude": "",
		"phone": "",
		"phone_dial": "",
		"whatsapp_url": "",
		"map_url": "",
		"directions_url": "",
	}


def payments_received_for(order) -> tuple:
	from shop.api.orders import payments_received

	received = payments_received([order.name]).get(order.name) or 0.0
	return flt(received), flt(order.grand_total)


def order_progress(order, shipment: dict | None) -> list[dict]:
	if order.docstatus == 2:
		return [{"label": _("Cancelled"), "done": "true"}]
	received, total = payments_received_for(order)
	fully_paid = total > 0 and received >= total - 0.005
	shipped = bool(shipment and shipment.get("shipped_on")) or (order.per_delivered or 0) >= 100
	delivered = bool(shipment and shipment.get("status") == "Delivered")
	if received > 0 and not fully_paid:
		# Advance orders: the prepayment milestone is done, the courier takes the balance.
		payment_label = _("Advance paid")
		paid = True
	else:
		paid = fully_paid or bool(order.get("advance_paid")) or has_payment(order.name)
		method = order.get("custom_payment_method") or ""
		if not paid and method == "advance":
			payment_label = _("Advance pending")
		elif not paid and method == "raast":
			# Settled by scanning the QR, never on delivery: naming the
			# advance rather than the transfer stops the customer waiting
			# for a courier to collect money they owe before the order ships.
			payment_label = _("Awaiting advance payment")
		else:
			payment_label = (
				_("Paid") if paid or expects_online_payment(order.name) else _("Payment on delivery")
			)
	if (order.get("custom_payment_method") or "") == "pickup":
		# No courier: the customer pays and collects in person, like COD at handover.
		stages = [
			(_("Order placed"), True),
			(_("Paid") if paid else _("Pay at pickup"), paid),
			(_("Ready for pickup"), paid),
			(_("Picked up"), paid),
		]
		return [{"label": label, "done": "true" if done else "false"} for label, done in stages]
	stages = [
		(_("Order placed"), True),
		(payment_label, paid),
		(_("Shipped"), shipped),
		(_("Delivered"), delivered),
	]
	return [{"label": label, "done": "true" if done else "false"} for label, done in stages]


def expects_online_payment(order_name: str) -> bool:
	return bool(
		frappe.db.exists(
			"Payment Request",
			{"reference_doctype": "Sales Order", "reference_name": order_name, "docstatus": 1},
		)
	)


def has_payment(order_name: str) -> bool:
	return bool(
		frappe.db.exists(
			"Payment Entry Reference",
			{"reference_doctype": "Sales Order", "reference_name": order_name, "docstatus": 1},
		)
	)


def shipment_summary(order_name: str) -> dict | None:
	rows = frappe.get_all(
		"Shop Fulfillment",
		filters={"sales_order": order_name, "status": ["!=", "Cancelled"]},
		fields=["name", "status", "carrier", "tracking_number", "tracking_url", "shipped_on"],
		order_by="creation desc",
		limit=1,
	)
	if not rows:
		return None
	shipment = rows[0]
	shipment.shipped_on = str(shipment.shipped_on) if shipment.shipped_on else None
	shipment.line = " · ".join(part for part in (shipment.carrier, shipment.tracking_number) if part)
	return shipment


def shipping_label(order) -> str:
	charge = sum(
		tax.tax_amount for tax in order.taxes if (tax.description or "").strip().lower() == "shipping"
	)
	return pricing.format_amount(charge) if charge else "Free"


def session_customers() -> list[str]:
	if frappe.session.user in ("Guest", None):
		return []
	contacts = frappe.get_all(
		"Contact Email", filters={"email_id": frappe.session.user}, pluck="parent"
	)
	if not contacts:
		return []
	return frappe.get_all(
		"Dynamic Link",
		filters={"parenttype": "Contact", "parent": ["in", contacts], "link_doctype": "Customer"},
		pluck="link_name",
	)
