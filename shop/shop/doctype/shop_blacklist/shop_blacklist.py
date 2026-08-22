import frappe
from frappe.model.document import Document


class ShopBlacklist(Document):
	def validate(self):
		if not (self.phone or self.email):
			frappe.throw("Phone or Email is required")
