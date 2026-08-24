import frappe
from frappe import _
from frappe.utils import cint, flt

from shop.api import only_managers

CHECK_FIELDS = frozenset((
	"enable_cod",
	"allow_out_of_stock",
	"prices_include_tax",
	"auto_send_to_fulfillment",
	"enable_fraud_check",
	"fraud_blacklist_blocks_all",
	"landmark_required",
))

INT_FIELDS = frozenset((
	"low_stock_threshold",
	"fraud_advance_threshold",
	"fraud_velocity_max",
	"fraud_risky_hour_start",
	"fraud_risky_hour_end",
	"fraud_auto_blacklist_failures",
	"fraud_rto_high_pct",
	"fraud_rto_medium_pct",
	"geocode_cache_ttl",
	"queue_schedule",
	"gms_concurrency",
))

CURRENCY_FIELDS = frozenset((
	"flat_shipping_rate",
	"free_shipping_above",
))

PASSWORD_FIELDS = frozenset((
	"fingerprint_secret_key",
	"ors_api_key",
))

EDITABLE = (
	"store_name",
	"store_logo",
	"enable_cod",
	"payment_gateway_account",
	"allow_out_of_stock",
	"prices_include_tax",
	"tax_template",
	"flat_shipping_rate",
	"free_shipping_above",
	"shipping_account",
	"low_stock_threshold",
	"price_list",
	"default_warehouse",
	"fulfillment_provider",
	"auto_send_to_fulfillment",
	"enable_fraud_check",
	"fraud_advance_threshold",
	"fraud_velocity_max",
	"fraud_risky_hour_start",
	"fraud_risky_hour_end",
	"fraud_auto_blacklist_failures",
	"fraud_blacklist_blocks_all",
	"fraud_rto_high_pct",
	"fraud_rto_medium_pct",
	"landmark_required",
	"address_country",
	"address_provinces",
	"address_cities",
	"fraud_signal_weights",
	"ors_api_key",
	"fingerprint_public_key",
	"fingerprint_secret_key",
	"fingerprint_region",
	"maps_provider",
	"gms_depth",
	"gms_concurrency",
	"geocode_cache_ttl",
	"queue_schedule",
)


@frappe.whitelist()
def get_settings() -> dict:
	only_managers()
	settings = frappe.get_doc("Shop Settings")
	payload = {}
	for field in EDITABLE:
		value = settings.get(field)
		# Password fields: never return the encrypted value; return empty
		# so the UI can show a placeholder instead of "******".
		if field in PASSWORD_FIELDS:
			try:
				value = settings.get_password(field, raise_exception=False) or ""
			except Exception:
				value = ""
		payload[field] = value
	payload.update(
		{
			"company": settings.company,
			"currency": settings.currency,
			"active_theme": settings.active_theme,
			"ors_api_key_set": bool(settings.get_password("ors_api_key", raise_exception=False)),
			"fingerprint_secret_key_set": bool(
				settings.get_password("fingerprint_secret_key", raise_exception=False)
			),
			"gateway_accounts": frappe.get_all(
				"Payment Gateway Account", fields=["name", "payment_gateway", "currency"]
			),
			"tax_templates": frappe.get_all("Sales Taxes and Charges Template", pluck="name"),
			"income_accounts": frappe.get_all(
				"Account",
				filters={"company": settings.company, "is_group": 0, "root_type": "Income"},
				pluck="name",
			),
			"price_lists": frappe.get_all("Price List", filters={"selling": 1}, pluck="name"),
			"fulfillment_providers": fulfillment_providers(),
			"warehouses": [
				{"value": row.name, "label": row.warehouse_name or row.name}
				for row in frappe.get_all(
					"Warehouse",
					filters={"company": settings.company, "is_group": 0},
					fields=["name", "warehouse_name"],
				)
			],
			"provinces": [
				{"name": row.name, "province_name": row.province_name, "cities": row.cities or ""}
				for row in (settings.province_table or [])
			],
		}
	)
	return payload


@frappe.whitelist()
def get_weight_schema() -> dict:
	"""Grouped signal-weight metadata + current effective values for the
	Fraud Weights editor."""
	only_managers()
	from shop.integrations.signal_weights import (
		DEFAULT_SIGNAL_WEIGHTS,
		WEIGHT_SCHEMA,
		get_weights,
	)

	settings = frappe.get_cached_doc("Shop Settings")
	current = get_weights(settings)

	groups = []
	for group, fields in WEIGHT_SCHEMA:
		rows = [
			{
				"key": key,
				"label": label,
				"default": DEFAULT_SIGNAL_WEIGHTS[key],
				"value": current[key],
			}
			for key, label in fields
		]
		groups.append({"group": group, "fields": rows})

	return {
		"groups": groups,
		"customized": bool(settings.fraud_signal_weights),
	}


def fulfillment_providers() -> list[dict]:
	from shop.fulfillment.provider import available

	return available()


@frappe.whitelist(methods=["POST"])
def save_settings(payload: dict) -> dict:
	only_managers()
	settings = frappe.get_doc("Shop Settings")
	for field in EDITABLE:
		if field not in payload:
			continue
		value = payload[field]
		if field in CHECK_FIELDS:
			value = 1 if value else 0
		elif field in INT_FIELDS:
			value = cint(value)
			if field == "gms_concurrency":
				value = max(1, min(8, value))
		elif field in CURRENCY_FIELDS:
			value = flt(value)
		elif field in PASSWORD_FIELDS:
			# Skip empty/masked values so the existing password is not wiped.
			if not value or value == "******":
				continue
		elif field == "queue_schedule":
			if value not in ("Every 10 Minutes", "Every 20 Minutes", "Hourly"):
				value = "Every 20 Minutes"
		elif field == "fraud_signal_weights":
			from shop.integrations.signal_weights import validate_weights_json

			try:
				value = validate_weights_json(value if isinstance(value, str) else "")
			except ValueError as exc:
				frappe.throw(_("Fraud signal weights: {0}").format(str(exc)))
		settings.set(field, value)
	settings.save(ignore_permissions=True)
	return get_settings()


@frappe.whitelist(methods=["POST"])
def save_provinces(provinces: list) -> dict:
	"""Save the province table. Each entry: {province_name, cities}."""
	only_managers()
	settings = frappe.get_doc("Shop Settings")
	settings.province_table = []
	for entry in provinces:
		prov_name = (entry.get("province_name") or "").strip()
		cities = (entry.get("cities") or "").strip()
		if not prov_name:
			continue
		settings.append("province_table", {"province_name": prov_name, "cities": cities})
	settings.save(ignore_permissions=True)
	return get_settings()


@frappe.whitelist()
def get_gms_status() -> dict:
	"""Get Google Maps Scraper status: installed, version, path."""
	only_managers()
	from shop.integrations.gms import get_gms_status as _get_status
	return _get_status()


@frappe.whitelist(methods=["POST"])
def download_gms(version: str | None = None) -> dict:
	"""Download or update Google Maps Scraper binary."""
	only_managers()
	from shop.integrations.gms import download_gms as _download
	return _download(version)
