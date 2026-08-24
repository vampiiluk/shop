import frappe


def execute():
	"""Sync every Custom Field declared in shop.hooks.custom_fields.

	Covers fields added after v1_single_verification (Sales Order
	custom_fraud_state / custom_payment_method / custom_ai_domain_scores,
	Shop Settings queue_schedule) and keeps older deployments aligned."""
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	from shop.hooks import custom_fields

	create_custom_fields(custom_fields, ignore_validate=True, update=True)
	frappe.db.commit()
