import frappe
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
))

CURRENCY_FIELDS = frozenset((
	"flat_shipping_rate",
	"free_shipping_above",
	"fingerprint_verify_above",
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
	"landmark_required",
	"pk_cities",
	"fingerprint_public_key",
	"fingerprint_secret_key",
	"ors_api_key",
	"fingerprint_region",
	"fingerprint_verify_above",
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
		}
	)
	return payload


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
		elif field in CURRENCY_FIELDS:
			value = flt(value)
		elif field in PASSWORD_FIELDS:
			# Skip empty/masked values so the existing password is not wiped.
			if not value or value == "******":
				continue
		settings.set(field, value)
	settings.save(ignore_permissions=True)
	return get_settings()
