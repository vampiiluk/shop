import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt

from shop import payments


class ShopSettings(Document):
	def validate(self):
		self.validate_advance_payment()
		self.validate_raast()

	def validate_advance_payment(self):
		if not self.enable_advance_payment:
			return
		if (self.advance_payment_mode or "Percent") == "Percent" and not 1 <= cint(
			self.advance_payment_percent
		) <= 100:
			frappe.throw(_("Advance Percent must be between 1 and 100."))
		if flt(self.advance_payment_flat or 0) < 0:
			frappe.throw(_("Advance Flat Amount cannot be negative."))

	def validate_raast(self):
		"""Store the IBAN canonicalised, and refuse one that would not scan.

		An empty IBAN is fine — it just leaves the method switched off at
		checkout — but a malformed one would encode a QR pointing at an account
		that does not exist, and nothing downstream would ever notice.
		"""
		iban = payments.normalize_iban(self.raast_iban)
		if iban and not payments.is_valid_iban(iban):
			frappe.throw(
				_("Raast IBAN looks wrong: {0} is not a valid 24-character Pakistani IBAN.").format(iban)
			)
		self.raast_iban = iban
