"""Backfill single-verification hashes after the landmark merge.

Runs post_model_sync. Hooks-defined custom fields have no automatic sync in
this app, so this patch creates/updates them itself.

1. Ensure the Address verification summary custom fields exist.
2. Move/create the Shop Settings GMS fields (incl. new gms_concurrency).
3. Backfill Address.custom_address_hash for all addresses (hash includes landmark).
4. Recompute Sales Order custom_address_hash from each order's shipping address.
5. Drop the obsolete Sales Order custom_landmark_hash + Shop Settings AI fields.
6. Drop leftover doctype columns (verification_type, landmark_risk_*).
7. Mark verification rows whose hash no longer matches any address as Skipped
   (the queue recreates them under the new hash).
"""

import frappe

from shop.integrations.geocoding import address_hash

ADDRESS_FIELDS = [
	{
		"fieldname": "custom_address_hash",
		"fieldtype": "Data",
		"label": "Address Verification Hash",
		"insert_after": "custom_alt_phone",
		"read_only": 1,
		"no_copy": 1,
		"print_hide": 1,
	},
	{
		"fieldname": "address_verification_section",
		"label": "Address Verification",
		"fieldtype": "Section Break",
		"insert_after": "custom_address_hash",
	},
	{
		"fieldname": "custom_verification_status",
		"label": "Verification Status",
		"fieldtype": "Select",
		"options": "\nPending\nComplete\nPartial\nFailed\nSkipped",
		"read_only": 1,
		"no_copy": 1,
		"insert_after": "address_verification_section",
	},
	{
		"fieldname": "custom_address_risk_score",
		"label": "Address Risk Score",
		"fieldtype": "Int",
		"read_only": 1,
		"no_copy": 1,
		"description": "Combined ORS + GMS verification risk (lower is better).",
		"insert_after": "custom_verification_status",
	},
	{
		"fieldname": "column_break_addr_verif",
		"fieldtype": "Column Break",
		"insert_after": "custom_address_risk_score",
	},
	{
		"fieldname": "custom_ors_confidence",
		"label": "Geocode Confidence",
		"fieldtype": "Data",
		"read_only": 1,
		"no_copy": 1,
		"insert_after": "column_break_addr_verif",
	},
	{
		"fieldname": "custom_latitude",
		"label": "Latitude",
		"fieldtype": "Float",
		"precision": "6",
		"read_only": 1,
		"no_copy": 1,
		"insert_after": "custom_ors_confidence",
	},
	{
		"fieldname": "custom_longitude",
		"label": "Longitude",
		"fieldtype": "Float",
		"precision": "6",
		"read_only": 1,
		"no_copy": 1,
		"insert_after": "custom_latitude",
	},
	{
		"fieldname": "custom_gms_result_count",
		"label": "Maps Results",
		"fieldtype": "Int",
		"read_only": 1,
		"no_copy": 1,
		"insert_after": "custom_longitude",
	},
	{
		"fieldname": "custom_last_verified_on",
		"label": "Last Verified On",
		"fieldtype": "Datetime",
		"read_only": 1,
		"no_copy": 1,
		"insert_after": "custom_gms_result_count",
	},
	{
		"fieldname": "custom_address_verification",
		"label": "Verification Record",
		"fieldtype": "Link",
		"options": "Shop Address Verification",
		"read_only": 1,
		"no_copy": 1,
		"insert_after": "custom_last_verified_on",
	},
]

SETTINGS_FIELDS = [
	{
		"fieldname": "maps_provider",
		"label": "Maps Provider",
		"fieldtype": "Select",
		"options": "\nGoogle Maps Scraper\nORS Geocoding\nNone",
		"default": "Google Maps Scraper",
		"insert_after": "landmark_required",
	},
	{
		"fieldname": "gms_depth",
		"label": "GMS Search Depth",
		"fieldtype": "Int",
		"default": "5",
		"insert_after": "maps_provider",
	},
	{
		"fieldname": "gms_concurrency",
		"label": "GMS Concurrency",
		"fieldtype": "Int",
		"default": "4",
		"insert_after": "gms_depth",
	},
	{
		"fieldname": "geocode_cache_ttl",
		"label": "Cache TTL (days)",
		"fieldtype": "Int",
		"default": "30",
		"insert_after": "gms_concurrency",
	},
	{
		"fieldname": "queue_schedule",
		"label": "Queue Schedule",
		"fieldtype": "Select",
		"default": "Every 20 Minutes",
		"options": "Every 10 Minutes\nEvery 20 Minutes\nHourly",
		"insert_after": "geocode_cache_ttl",
	},
]

LEFTOVER_COLUMNS = {
	"verification_type",
	"landmark_risk_status",
	"landmark_risk_score",
	"landmark_risk_json",
}


def execute():
	_ensure_custom_fields()
	valid = _backfill_addresses()
	_recompute_orders(valid)
	_drop_obsolete_fields()
	_drop_leftover_columns()
	_invalidate_orphans(valid)


def _ensure_custom_fields():
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	create_custom_fields({
		"Address": ADDRESS_FIELDS,
		"Shop Settings": SETTINGS_FIELDS,
	}, ignore_validate=True)


def _backfill_addresses() -> set:
	rows = frappe.get_all(
		"Address",
		fields=["name", "address_line1", "address_line2", "city", "pincode",
			"custom_landmark", "custom_address_hash"],
	)
	valid = set()
	for row in rows:
		hkey = address_hash(_addr_dict(row))
		valid.add(hkey)
		if row.custom_address_hash != hkey:
			frappe.db.set_value("Address", row.name, "custom_address_hash", hkey,
				update_modified=False)
	return valid


def _recompute_orders(valid: set):
	rows = frappe.get_all(
		"Sales Order",
		filters={"shipping_address_name": ("is", "set")},
		fields=["name", "shipping_address_name", "custom_address_hash"],
	)
	for row in rows:
		addr_hash = frappe.db.get_value("Address", row.shipping_address_name,
			"custom_address_hash")
		if addr_hash and addr_hash != row.custom_address_hash:
			frappe.db.set_value("Sales Order", row.name, "custom_address_hash", addr_hash,
				update_modified=False)


def _drop_obsolete_fields():
	for dt, fieldname in (
		("Sales Order", "custom_landmark_hash"),
		("Shop Settings", "ai_section"),
		("Shop Settings", "ai_scoring_model"),
	):
		name = frappe.db.get_value("Custom Field", {"dt": dt, "fieldname": fieldname})
		if name:
			frappe.delete_doc("Custom Field", name, ignore_permissions=True)


def _drop_column_if_exists(table: str, column: str):
	existing = {c[0] for c in frappe.db.sql(f"DESCRIBE `{table}`")}
	if column in existing:
		frappe.db.sql_ddl(f"ALTER TABLE `{table}` DROP COLUMN `{column}`")


def _drop_leftover_columns():
	_drop_column_if_exists("tabSales Order", "custom_landmark_hash")
	# Shop Settings is a Single: values live in tabSingles, not columns
	frappe.db.sql(
		"""DELETE FROM `tabSingles`
		WHERE doctype = 'Shop Settings' AND field IN ('ai_section', 'ai_scoring_model')"""
	)
	for col in LEFTOVER_COLUMNS & {c[0] for c in frappe.db.sql("DESCRIBE `tabShop Address Verification`")}:
		frappe.db.sql_ddl(f"ALTER TABLE `tabShop Address Verification` DROP COLUMN `{col}`")


def _invalidate_orphans(valid: set):
	if not valid:
		return
	orphan_rows = frappe.db.sql(
		"""SELECT name FROM `tabShop Address Verification`
		WHERE address_hash IS NOT NULL AND address_hash NOT IN %(valid)s""",
		{"valid": tuple(valid)},
	)
	for (name,) in orphan_rows:
		frappe.db.set_value("Shop Address Verification", name, "status", "Skipped",
			update_modified=False)


def _addr_dict(row) -> dict:
	return {
		"address_line1": row.address_line1 or "",
		"address_line2": row.address_line2 or "",
		"city": row.city or "",
		"pincode": row.pincode or "",
		"landmark": row.get("custom_landmark") or "",
	}


