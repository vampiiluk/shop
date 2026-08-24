"""Delete Landmark-type verification rows before the verification_type
column is dropped by the schema sync."""

import frappe


def execute():
	frappe.db.sql(
		"DELETE FROM `tabShop Address Verification` WHERE verification_type = 'Landmark'"
	)
