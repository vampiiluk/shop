import frappe
from erpnext.accounts.doctype.payment_request.payment_request import PaymentRequest

AUTHORIZED_STATUSES = ("Authorized", "Verified", "Completed")


class ShopPaymentRequest(PaymentRequest):
	def on_payment_authorized(self, status: str | None = None) -> str | None:
		"""Called by payments gateway controllers after a successful payment."""
		if status not in AUTHORIZED_STATUSES:
			return None
		self.flags.ignore_permissions = True
		if self.status != "Paid":
			self.set_as_paid()
		if self.reference_doctype == "Sales Order":
			from shop.fulfillment.service import auto_send
			from shop.api.orders import create_sales_invoice_for_order, payment_entries_for_order, billed_invoice_for_order

			auto_send(self.reference_name)
			try:
				invoice_name = create_sales_invoice_for_order(self.reference_name)
				if invoice_name:
					_allocate_payment_to_invoice(self.reference_name, invoice_name)
			except Exception:
				frappe.log_error(
					title="Storefront auto-invoice failed",
					reference_doctype="Sales Order",
					reference_name=self.reference_name,
				)
		return self.confirmation_url()

	def confirmation_url(self) -> str | None:
		if self.reference_doctype != "Sales Order":
			return None
		token = frappe.db.get_value("Shop Cart", {"sales_order": self.reference_name}, "token")
		if token:
			return f"/order-confirmation/{self.reference_name}?token={token}"
		return "/account/orders"


def _allocate_payment_to_invoice(order_name: str, invoice_name: str) -> None:
	"""Re-point any payment received against the order at its invoice.

	The gateway payment entry references the Sales Order (the Payment
	Request's reference). The entry is recreated against the Sales Invoice
	so the invoice is marked paid and AR stays balanced. The gateway capture
	is unaffected - only the book entry changes.
	"""
	for payment in payment_entries_for_order(order_name):
		pe = frappe.get_doc("Payment Entry", payment)
		pe.flags.ignore_permissions = True
		if any(
			ref.reference_doctype == "Sales Invoice" and ref.reference_name == invoice_name
			for ref in pe.references
		):
			continue
		if not any(
			ref.reference_doctype == "Sales Order" and ref.reference_name == order_name
			for ref in pe.references
		):
			continue
		pe.cancel()
		replacement = frappe.get_doc(
			{
				"doctype": "Payment Entry",
				"payment_type": "Receive",
				"party_type": pe.party_type,
				"party": pe.party,
				"company": pe.company,
				"paid_from": pe.paid_from,
				"paid_to": pe.paid_to,
				"paid_amount": pe.paid_amount,
				"received_amount": pe.received_amount,
				"mode_of_payment": pe.mode_of_payment,
				"reference_no": pe.reference_no,
				"reference_date": pe.reference_date,
				"remarks": pe.remarks,
				"references": [
					{
						"reference_doctype": "Sales Invoice",
						"reference_name": invoice_name,
						"allocated_amount": pe.paid_amount,
					}
				],
			}
		)
		replacement.flags.ignore_permissions = True
		replacement.insert(ignore_permissions=True)
		replacement.submit()
