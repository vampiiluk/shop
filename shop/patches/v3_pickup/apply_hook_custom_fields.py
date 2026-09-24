import frappe


def execute():
	"""Sync every Custom Field declared in shop.hooks.custom_fields.

	v3 adds Sales Order custom_pickup_location so pickup orders remember the
	location the customer chose at checkout."""
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	from shop.hooks import custom_fields

	create_custom_fields(custom_fields, ignore_validate=True, update=True)
	frappe.db.commit()
