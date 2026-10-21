import frappe


def execute():
	"""Sync every Custom Field declared in shop.hooks.custom_fields.

	A hand-placed order writes down the coupon it used, so the desk can
	show it and the books can be checked against it later.
	"""
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	from shop.hooks import custom_fields

	create_custom_fields(custom_fields, ignore_validate=True, update=True)
	frappe.db.commit()
