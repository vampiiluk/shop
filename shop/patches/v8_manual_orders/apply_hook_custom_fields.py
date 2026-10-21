import frappe


def execute():
	"""Sync every Custom Field declared in shop.hooks.custom_fields.

	v8 adds Sales Order custom_manual_order and custom_order_notes, so a
	hand-placed order can be told apart from one the site took and can carry
	the note the merchant took it with.
	"""
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	from shop.hooks import custom_fields

	create_custom_fields(custom_fields, ignore_validate=True, update=True)
	frappe.db.commit()
