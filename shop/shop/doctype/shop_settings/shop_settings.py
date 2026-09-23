import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt


class ShopSettings(Document):
	def validate(self):
		if not self.enable_advance_payment:
			return
		if (self.advance_payment_mode or "Percent") == "Percent" and not 1 <= cint(
			self.advance_payment_percent
		) <= 100:
			frappe.throw(_("Advance Percent must be between 1 and 100."))
		if flt(self.advance_payment_flat or 0) < 0:
			frappe.throw(_("Advance Flat Amount cannot be negative."))
