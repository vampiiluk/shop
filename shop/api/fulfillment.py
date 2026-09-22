import frappe
from frappe import _

from shop.api import only_managers
from shop.fulfillment import service
from shop.fulfillment.provider import available, get_provider


@frappe.whitelist()
def get_providers() -> list[dict]:
	only_managers()
	return available()


@frappe.whitelist()
def get_fulfillment(order: str) -> dict | None:
	only_managers()
	return service.for_order(order)


@frappe.whitelist(methods=["POST"])
def send_order(order: str, provider: str | None = None) -> dict:
	only_managers()
	return service.summary(service.send(order, provider))


@frappe.whitelist(methods=["POST"])
def sync_fulfillment(fulfillment: str) -> dict:
	only_managers()
	return service.sync(fulfillment)


@frappe.whitelist(methods=["POST"])
def cancel_fulfillment(fulfillment: str) -> dict:
	only_managers()
	return service.cancel(fulfillment)


@frappe.whitelist(methods=["POST"])
def mark_shipped(fulfillment: str, carrier: str | None = None, tracking_number: str | None = None) -> dict:
	"""Record a shipment you packed yourself, with optional tracking."""
	only_managers()
	doc = frappe.get_doc("Shop Fulfillment", fulfillment)
	provider = get_provider(doc.provider)
	if not hasattr(provider, "mark_shipped"):
		frappe.throw(_("{0} reports shipping automatically").format(provider.label))
	service.apply_result(doc, provider.mark_shipped(doc, carrier, tracking_number))
	return service.summary(doc)


@frappe.whitelist(methods=["POST"])
def mark_delivery_outcome(order: str, outcome: str) -> dict:
	"""Record a delivery result. Feeds the fraud engine: city RTO stats,
	customer failure counts and auto-blacklisting all learn from this."""
	only_managers()
	from shop.integrations import fraud

	return fraud.record_delivery_outcome(order, outcome)


@frappe.whitelist(methods=["POST"])
def mark_delivered(fulfillment: str) -> dict:
	"""Mark a shipped fulfillment as delivered. Files the delivery note if
	needed and records the outcome for fraud tracking."""
	only_managers()
	doc = frappe.get_doc("Shop Fulfillment", fulfillment)
	if doc.status not in ("Shipped", "Delivered"):
		frappe.throw(_("Only shipped fulfillments can be marked as delivered"))
	if doc.status != "Delivered":
		service.apply_result(doc, {"status": "Delivered"})
	# Record delivery outcome for fraud
	try:
		from shop.integrations import fraud
		fraud.record_delivery_outcome(doc.sales_order, "Delivered")
	except Exception:
		frappe.log_error(title="Delivery outcome recording failed")
	return service.summary(doc)


@frappe.whitelist(methods=["POST"])
def unmark_delivered(fulfillment: str) -> dict:
	"""Revert a delivered fulfillment back to Shipped: clears the timestamps,
	forgets the fraud outcome, and cancels the delivery note the delivered
	transition itself filed when the order never actually shipped."""
	only_managers()
	doc = frappe.get_doc("Shop Fulfillment", fulfillment)
	if doc.status != "Delivered":
		frappe.throw(_("Only delivered fulfillments can be unmarked"))
	# A fulfillment that never passed through Shipped got its delivery note
	# from the delivered transition itself; one that shipped keeps its note,
	# because the goods really did leave the warehouse.
	never_shipped = not doc.shipped_on
	# Sales Order has no delivered_on column of its own — the order-level
	# delivery date is derived from the delivery note, which stays put for a
	# shipped order. Clear the fulfillment's own stamp here: apply_result only
	# touches timestamps for statuses it is asked to set, so assign first and
	# let its save persist the clear.
	doc.delivered_on = None
	service.apply_result(doc, {"status": "Shipped"})
	try:
		from shop.integrations import fraud

		fraud.reset_delivery_outcome(doc.sales_order)
	except Exception:
		frappe.log_error(title="Resetting delivery outcome failed")
	if never_shipped:
		cancel_delivery_notes(doc.sales_order)
	return service.summary(doc)


def cancel_delivery_notes(order: str) -> None:
	"""Cancel submitted delivery notes filed against an order. Notes already
	invoiced are skipped: ERPNext blocks the cancel and the ledger should
	stay honest about what was billed."""
	notes = frappe.get_all(
		"Delivery Note Item",
		filters={"against_sales_order": order, "docstatus": 1},
		pluck="parent",
		distinct=True,
	)
	for name in notes:
		try:
			note = frappe.get_doc("Delivery Note", name)
			note.flags.ignore_permissions = True
			note.cancel()
		except Exception:
			frappe.log_error(
				title="Cancelling delivery note failed",
				reference_doctype="Delivery Note",
				reference_name=name,
			)
	frappe.db.commit()


@frappe.whitelist()
def list_fulfillments(status: str | None = None, start: int = 0, limit: int = 20) -> dict:
	only_managers()
	filters = {"status": status} if status else {}
	names = frappe.get_all(
		"Shop Fulfillment",
		filters=filters,
		pluck="name",
		order_by="creation desc",
		start=frappe.utils.cint(start),
		limit=min(frappe.utils.cint(limit) or 20, 100),
	)
	return {
		"fulfillments": [service.summary(name) for name in names],
		"total": frappe.db.count("Shop Fulfillment", filters=filters),
	}
