import frappe
from frappe import _
from frappe.utils import cint, flt

from shop.api import only_managers
from shop.storefront import pricing

MAX_SCAN = 500

DISPLAY_STATUS = {
	"To Deliver and Bill": "Open",
	"To Deliver": "Open",
	"To Pay": "Open",
	"To Bill": "Fulfilled",
	"On Hold": "On hold",
}

STATUS_FILTERS = {
	"Open": ["To Deliver and Bill", "To Deliver", "To Pay"],
	"Fulfilled": ["To Bill"],
	"Completed": ["Completed"],
}

LIST_FIELDS = [
	"name",
	"customer",
	"customer_name",
	"transaction_date",
	"delivery_date",
	"status",
	"grand_total",
	"per_delivered",
	"docstatus",
	"contact_email",
	"custom_fraud_score",
	"custom_fraud_verdict",
	"custom_payment_method",
]


@frappe.whitelist()
def get_orders(
	status: str | None = None,
	payment: str | None = None,
	search: str | None = None,
	start: int = 0,
	limit: int = 20,
) -> dict:
	only_managers()
	filters = {"docstatus": ["<", 2]} if status != "Cancelled" else {"docstatus": 2}
	if status in STATUS_FILTERS:
		filters["status"] = ["in", STATUS_FILTERS[status]]
	or_filters = None
	if search:
		term = f"%{search.strip()}%"
		or_filters = [["name", "like", term], ["customer_name", "like", term], ["contact_email", "like", term]]
	matched = frappe.get_all(
		"Sales Order",
		filters=filters,
		or_filters=or_filters,
		fields=LIST_FIELDS,
		order_by="creation desc",
		limit=MAX_SCAN,
	)
	decorate(matched)
	if payment:
		matched = [order for order in matched if order["payment_status"] == payment]
	start, limit = cint(start), min(cint(limit) or 20, 100)
	return {
		"orders": matched[start : start + limit],
		"total": len(matched),
		"statuses": [*STATUS_FILTERS, "Cancelled"],
	}


def decorate(orders: list) -> None:
	received_map = payments_received([order.name for order in orders])
	for order in orders:
		order["formatted_total"] = pricing.format_amount(order.grand_total)
		order["display_status"] = DISPLAY_STATUS.get(order.status, order.status)
		received = flt(received_map.get(order.name))
		total = flt(order.grand_total)
		order["payment_status"] = payment_status_label(order.get("custom_payment_method"), received, total)
		order["payment_received"] = received
		order["payment_balance"] = max(total - received, 0.0)
		order["fulfillment_status"] = fulfillment_label(order)


def fulfillment_label(order) -> str:
	if order.docstatus == 2:
		return "Cancelled"
	if flt(order.per_delivered) >= 100:
		return "Fulfilled"
	if flt(order.per_delivered) > 0:
		return "Partly fulfilled"
	return "Unfulfilled"


def paid_orders(names: list[str]) -> set:
	"""Sales Orders settled by a submitted Payment Entry.

	Payments may reference the order directly (advance) or its submitted
	Sales Invoices (post-payment allocation), so both are considered and
	invoice references are mapped back to their orders.
	"""
	if not names:
		return set()
	invoices = frappe.get_all(
		"Sales Invoice Item",
		filters={"sales_order": ["in", names], "docstatus": 1},
		pluck="parent",
	)
	references = [*names, *invoices]
	rows = frappe.db.sql(
		"""
		SELECT reference_name FROM `tabPayment Entry Reference`
		WHERE docstatus = 1 AND reference_name IN %(references)s
		""",
		{"references": references},
		as_dict=True,
	)
	paid = {row.reference_name for row in rows}
	settled = paid & set(names)
	if invoices:
		paid_invoices = paid & set(invoices)
		if paid_invoices:
			settled.update(
				frappe.get_all(
					"Sales Invoice Item",
					filters={"parent": ["in", list(paid_invoices)], "docstatus": 1},
					pluck="sales_order",
				)
			)
	return settled


def payments_received(names: list[str]) -> dict:
	"""Total allocated Payment Entry amount per Sales Order.

	Payments may reference the order directly (advance) or its submitted
	Sales Invoices (auto-billing), so both are summed and invoice references
	mapped back to their orders.
	"""
	if not names:
		return {}
	invoices = frappe.get_all(
		"Sales Invoice Item",
		filters={"sales_order": ["in", names], "docstatus": 1},
		fields=["parent", "sales_order"],
	)
	by_invoice = {row.parent: row.sales_order for row in invoices}
	references = [*names, *by_invoice]
	received = {name: 0.0 for name in names}
	if not references:
		return received
	rows = frappe.db.sql(
		"""
		SELECT reference_name, SUM(allocated_amount) AS allocated
		FROM `tabPayment Entry Reference`
		WHERE docstatus = 1 AND reference_name IN %(references)s
		GROUP BY reference_name
		""",
		{"references": references},
		as_dict=True,
	)
	for row in rows:
		order_name = row.reference_name if row.reference_name in received else by_invoice.get(row.reference_name)
		if order_name in received:
			received[order_name] += flt(row.allocated)
	return received


def payment_status_label(method, received, total) -> str:
	"""Tri-state payment status: Unpaid, Advance Received / Partially Paid, Paid."""
	received, total = flt(received), flt(total)
	if total > 0 and received >= total - 0.005:
		return "Paid"
	if received > 0:
		return "Advance Received" if (method or "cod") == "advance" else "Partially Paid"
	return "Unpaid"


def billed_invoice_for_order(order_name: str) -> str | None:
	"""Submitted Sales Invoice linked to the order, if any."""
	return frappe.db.get_value(
		"Sales Invoice Item",
		{"sales_order": order_name, "docstatus": 1},
		"parent",
		order_by="modified desc",
	)


def auto_billing_enabled() -> bool:
	"""Whether storefront orders are billed automatically."""
	return frappe.db.get_single_value("Shop Settings", "auto_bill_on_payment") != 0


def create_sales_invoice_for_order(order_name: str) -> str | None:
	"""Create and submit the Sales Invoice for an order (auto-billing).

	Runs when an order is paid (prepaid) or delivered (COD) so it stops
	showing "To Bill". The invoice is submitted so payment can be allocated
	to it and AR stays balanced, but it is gated from FBR e-invoicing
	(custom_submit_to_fbr = 0): nothing reaches the tax authority without a
	reviewed submission. Idempotent - an existing submitted invoice against
	the order is never duplicated.
	"""
	order = frappe.get_doc("Sales Order", order_name)
	if order.docstatus != 1:
		return None
	existing = billed_invoice_for_order(order_name)
	if existing:
		return existing
	from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice

	invoice = make_sales_invoice(order_name)
	invoice.flags.ignore_permissions = True
	if not invoice.get("items"):
		return None
	if invoice.meta.has_field("custom_submit_to_fbr"):
		invoice.custom_submit_to_fbr = 0
	if invoice.meta.has_field("custom_province") and not invoice.custom_province:
		# FBR's Seller Province is mandatory; fetch_from only runs on the
		# form, so server-side inserts must pull it from the company.
		invoice.custom_province = frappe.db.get_value(
			"Company", invoice.company, "custom_province"
		)
	invoice.insert(ignore_permissions=True)
	invoice.submit()
	return invoice.name


@frappe.whitelist()
def get_order(name: str) -> dict:
	only_managers()
	order = frappe.get_doc("Sales Order", name)
	received = payments_received([order.name]).get(order.name) or 0.0
	total = flt(order.grand_total)
	balance = max(total - received, 0.0)
	advance = flt(order.custom_advance_amount or 0)
	courier = max(total - max(received, min(advance, total)), 0.0)
	return {
		"name": order.name,
		"customer": order.customer,
		"customer_name": order.customer_name,
		"contact_email": order.contact_email,
		"transaction_date": str(order.transaction_date),
		"delivery_date": str(order.delivery_date) if order.delivery_date else None,
		"status": order.status,
		"display_status": "Cancelled" if order.docstatus == 2 else DISPLAY_STATUS.get(order.status, order.status),
		"docstatus": order.docstatus,
		"payment_status": payment_status_label(order.custom_payment_method, received, total),
		"payment_method": order.custom_payment_method or "cod",
		"payment_received": received,
		"payment_balance": balance,
		"advance_amount": advance,
		"courier_balance": courier,
		"formatted_payment_received": pricing.format_amount(received),
		"formatted_payment_balance": pricing.format_amount(balance),
		"formatted_advance_amount": pricing.format_amount(advance),
		"formatted_courier_balance": pricing.format_amount(courier),
		"fulfillment_status": fulfillment_label(order),
		"delivery_outcome": order.custom_delivery_outcome or "",
		"fraud_verdict": order.custom_fraud_verdict or "",
		"fraud_score": order.custom_fraud_score or 0,
		"address": address_display(order.shipping_address_name),
		"formatted_total": pricing.format_amount(order.total),
		"formatted_discount": pricing.format_amount(order.discount_amount) if order.discount_amount else None,
		"formatted_grand_total": pricing.format_amount(order.grand_total),
		"items": [
			{
				"item_code": row.item_code,
				"item_name": row.item_name,
				"qty": row.qty,
				"formatted_rate": pricing.format_amount(row.rate),
				"formatted_amount": pricing.format_amount(row.amount),
			}
			for row in order.items
		],
		"timeline": timeline(order),
	}


def timeline(order) -> list[dict]:
	events = [{"label": "Order placed", "on": str(order.creation)[:16]}]
	# Payments may land on the order itself (COD/advance) or on the invoice
	# auto-billing created at placement - accept either and show the first.
	invoices = frappe.get_all(
		"Sales Invoice Item",
		filters={"sales_order": order.name, "docstatus": 1},
		pluck="parent",
		distinct=True,
	)
	payments = frappe.get_all(
		"Payment Entry Reference",
		filters={
			"docstatus": 1,
			"reference_doctype": ["in", ["Sales Order", "Sales Invoice"]],
			"reference_name": ["in", [order.name, *invoices]],
		},
		pluck="parent",
		distinct=True,
	)
	if payments:
		created = frappe.get_all(
			"Payment Entry",
			filters={"name": ["in", payments]},
			fields=["creation"],
			order_by="creation asc",
			limit=1,
		)
		events.append({"label": "Payment recorded", "on": str(created[0].creation)[:16]})
	for note in frappe.get_all(
		"Delivery Note Item",
		filters={"against_sales_order": order.name, "docstatus": 1},
		fields=["parent", "creation"],
		group_by="parent",
	):
		events.append({"label": "Fulfilled", "on": str(note.creation)[:16]})
	if order.docstatus == 2:
		events.append({"label": "Order cancelled", "on": str(order.modified)[:16]})
	return events


def address_display(name: str | None) -> str | None:
	if not name:
		return None
	from frappe.contacts.doctype.address.address import get_address_display

	return get_address_display(name)


@frappe.whitelist(methods=["POST"])
def mark_paid(name: str, mode_of_payment: str | None = None) -> dict:
	only_managers()
	from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

	received = payments_received([name]).get(name) or 0.0
	total = flt(frappe.get_cached_value("Sales Order", name, "grand_total"))
	if total > 0 and received >= total - 0.005:
		frappe.throw(_("This order is already paid in full"))
	invoice_name = billed_invoice_for_order(name)
	if not invoice_name and auto_billing_enabled():
		invoice_name = create_sales_invoice_for_order(name)
	entry = get_payment_entry("Sales Invoice" if invoice_name else "Sales Order", invoice_name or name)
	if mode_of_payment:
		entry.mode_of_payment = mode_of_payment
	entry.reference_no = name
	entry.reference_date = frappe.utils.nowdate()
	entry.flags.ignore_permissions = True
	entry.insert(ignore_permissions=True)
	entry.submit()
	from shop.fulfillment.service import auto_send

	auto_send(name)
	return get_order(name)


@frappe.whitelist(methods=["POST"])
def mark_advance_received(
	name: str,
	amount: float | None = None,
	mode_of_payment: str | None = None,
	reference_no: str | None = None,
) -> dict:
	"""Record the advance the customer transferred so the order can ship.

	Manual bank/wallet flow: the shopper pays the account listed in Shop
	Settings, the merchant records it here, auto-fulfillment fires like a
	paid order, and the courier collects the remaining balance on delivery.
	"""
	only_managers()
	from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

	order = frappe.get_doc("Sales Order", name)
	if order.docstatus != 1:
		frappe.throw(_("Only submitted orders can receive payments"))
	total = flt(order.grand_total)
	received = payments_received([name]).get(name) or 0.0
	due = total - received
	if due <= 0.005:
		frappe.throw(_("This order is already paid in full"))
	advance_due = max(flt(order.custom_advance_amount or 0) - received, 0.0)
	target = flt(amount) if amount else (advance_due or due)
	if target <= 0:
		frappe.throw(_("Payment amount must be greater than zero"))
	if target > due + 0.005:
		frappe.throw(
			_("Amount {0} exceeds the outstanding balance {1}").format(
				pricing.format_amount(target), pricing.format_amount(due)
			)
		)
	target = min(target, due)
	invoice_name = billed_invoice_for_order(name)
	if not invoice_name and auto_billing_enabled():
		invoice_name = create_sales_invoice_for_order(name)
	entry = get_payment_entry("Sales Invoice" if invoice_name else "Sales Order", invoice_name or name)
	entry.paid_amount = target
	entry.received_amount = target
	if entry.references:
		entry.references[0].allocated_amount = target
	if mode_of_payment:
		entry.mode_of_payment = mode_of_payment
	entry.reference_no = reference_no or name
	entry.reference_date = frappe.utils.nowdate()
	entry.flags.ignore_permissions = True
	entry.insert(ignore_permissions=True)
	entry.submit()
	from shop.fulfillment.service import auto_send

	auto_send(name)
	return get_order(name)


@frappe.whitelist()
def payment_modes() -> list[str]:
	only_managers()
	return frappe.get_all("Mode of Payment", pluck="name", order_by="name")


@frappe.whitelist(methods=["POST"])
def fulfill(name: str) -> dict:
	only_managers()
	from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note

	order = frappe.get_doc("Sales Order", name)
	if order.docstatus != 1:
		frappe.throw(_("Only submitted orders can be fulfilled"))
	if flt(order.per_delivered) >= 100:
		frappe.throw(_("This order is already fulfilled"))
	note = make_delivery_note(name)
	note.flags.ignore_permissions = True
	note.insert(ignore_permissions=True)
	note.submit()
	if auto_billing_enabled() and not billed_invoice_for_order(name):
		try:
			create_sales_invoice_for_order(name)
		except Exception:
			frappe.log_error(
				title="Storefront auto-invoice failed",
				reference_doctype="Sales Order",
				reference_name=name,
			)
	return get_order(name)


def invoices_for_order(order_name: str) -> list[str]:
	return frappe.get_all(
		"Sales Invoice Item",
		filters={"sales_order": order_name, "docstatus": ["<", 2]},
		pluck="parent",
		distinct=True,
	)


def payment_entries_for_order(order_name: str) -> list[str]:
	invoices = invoices_for_order(order_name)
	references = [order_name, *invoices]
	if not references:
		return []
	rows = frappe.db.sql(
		"""
		SELECT DISTINCT parent FROM `tabPayment Entry Reference`
		WHERE docstatus = 1 AND reference_name IN %(references)s
		""",
		{"references": references},
		as_list=True,
	)
	return [row[0] for row in rows]


def gateway_payment(payment_entry) -> bool:
	"""True when the Payment Entry was funded through a payment gateway.

	Gateway-funded entries carry the originating Payment Request on their
	reference rows; manual/cash entries do not.
	"""
	return bool(
		frappe.db.get_value(
			"Payment Entry Reference",
			{"parent": payment_entry.name, "payment_request": ["!=", ""]},
			"name",
		)
	)


def _refund_gateway_payment(payment_entry) -> None:
	"""Refund a gateway-funded payment through the gateway itself.

	Cancelling the Payment Entry only reverses the books - the customer
	stays charged. The gateway integration (Stripe/Razorpay/...) exposes
	refund_payment() which pushes the money back. Refund first, then cancel
	the entry so the reversal is complete.
	"""
	request = frappe.db.get_value(
		"Payment Entry Reference",
		{"parent": payment_entry.name, "payment_request": ["!=", ""]},
		"payment_request",
	)
	gateway_account = frappe.db.get_value("Payment Request", request, "payment_gateway_account") if request else None
	if not request or not gateway_account:
		frappe.throw(
			_("Payment {0} was made online. Process the refund manually before cancelling the order.").format(
				payment_entry.name
			)
		)
	account = frappe.get_doc("Payment Gateway Account", gateway_account)
	integration_doctype = account.payment_gateway
	if not integration_doctype or not frappe.db.exists("DocType", integration_doctype):
		frappe.throw(
			_("Gateway integration {0} is not installed. Process the refund manually before cancelling the order.").format(
				integration_doctype
			)
		)
	settings = frappe.get_all(integration_doctype, limit=1, order_by="creation asc")
	if not settings:
		frappe.throw(
			_("Gateway {0} is not set up. Process the refund manually before cancelling the order.").format(
				integration_doctype
			)
		)
	integration = frappe.get_doc(integration_doctype, settings[0].name)
	refund = getattr(integration, "refund_payment", None)
	if not callable(refund):
		frappe.throw(
			_("Gateway {0} does not support refunds from here. Process the refund manually before cancelling.").format(
				integration_doctype
			)
		)
	refund(payment_entry)
	payment_entry.cancel()


def fbr_submitted(invoice) -> bool:
	"""True when the invoice was accepted by FBR and cannot be cancelled.

	Mirrors the FBR app's own cancel guard (gated on the Company-level
	enable switch) without importing the app. The meta guard keeps the
	shop working when the FBR app is not installed at all.
	"""
	if not frappe.get_meta("Company").has_field("custom_fbr_enabled"):
		return False
	if not frappe.db.get_value("Company", invoice.company, "custom_fbr_enabled"):
		return False
	status = (invoice.get("custom_fbr_status") or "").strip().lower()
	return status == "valid" and bool(invoice.get("custom_fbr_invoice_number"))


def _credit_note_for(invoice) -> None:
	"""Reverse a submitted invoice with a Credit Note (return invoice).

	Required once an invoice has been accepted by FBR: the original is
	legally on file and cannot be cancelled.
	"""
	from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_sales_return

	return_invoice = make_sales_return(invoice.name)
	return_invoice.flags.ignore_permissions = True
	if return_invoice.meta.has_field("custom_submit_to_fbr"):
		return_invoice.custom_submit_to_fbr = 0
	return_invoice.insert(ignore_permissions=True)
	return_invoice.submit()


def _reverse_invoice(invoice) -> None:
	invoice.flags.ignore_permissions = True
	if invoice.docstatus == 0:
		invoice.delete()
	elif fbr_submitted(invoice):
		_credit_note_for(invoice)
	else:
		invoice.cancel()


@frappe.whitelist(methods=["POST"])
def cancel_order(name: str) -> dict:
	only_managers()
	# Reverse the full chain so cancellation works for invoiced/delivered
	# orders too: payments first, then Sales Invoices, then Delivery Notes,
	# then the Sales Order itself.
	order = frappe.get_doc("Sales Order", name)
	if order.docstatus != 1:
		frappe.throw(_("Only submitted orders can be cancelled"))
	# Money first: gateway-funded payments are refunded through the gateway
	# (cancelling the entry alone would leave the customer charged); manual
	# payments are reversed as the cash is returned.
	for payment in payment_entries_for_order(name):
		pe = frappe.get_doc("Payment Entry", payment)
		pe.flags.ignore_permissions = True
		if gateway_payment(pe):
			_refund_gateway_payment(pe)
		else:
			pe.cancel()
	# Invoices: unpaid ones cancel directly. Invoices already accepted by
	# FBR cannot be cancelled - they are reversed with a Credit Note.
	for invoice in invoices_for_order(name):
		_reverse_invoice(frappe.get_doc("Sales Invoice", invoice))
	for (note,) in frappe.db.sql(
		"SELECT DISTINCT parent FROM `tabDelivery Note Item` WHERE against_sales_order=%s AND docstatus=1", name
	):
		dn = frappe.get_doc("Delivery Note", note)
		dn.flags.ignore_permissions = True
		dn.cancel()
	order = frappe.get_doc("Sales Order", name)
	order.flags.ignore_permissions = True
	order.cancel()
	return get_order(name)
