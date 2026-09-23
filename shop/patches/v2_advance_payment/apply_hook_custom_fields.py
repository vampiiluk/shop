import frappe


def execute():
	"""Sync every Custom Field declared in shop.hooks.custom_fields.

	v2 adds Sales Order custom_advance_amount alongside the existing payment
	method field so advance orders can record what the customer owes upfront."""
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	from shop.hooks import custom_fields

	create_custom_fields(custom_fields, ignore_validate=True, update=True)
	frappe.db.commit()
