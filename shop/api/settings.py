import frappe
from frappe import _
from frappe.utils import cint, flt

from shop.api import only_managers

CHECK_FIELDS = frozenset((
	"enable_cod",
	"enable_pickup",
	"auto_bill_on_payment",
	"enable_advance_payment",
	"enable_raast_qr",
	"allow_out_of_stock",
	"prices_include_tax",
	"auto_send_to_fulfillment",
	"enable_fraud_check",
	"fraud_blacklist_blocks_all",
	"landmark_required",
	"gms_enabled",
	"ors_enabled",
	"ip_intel_enabled",
	"meta_enabled",
))

INT_FIELDS = frozenset((
	"low_stock_threshold",
	"advance_payment_percent",
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
	"advance_payment_flat",
))

PASSWORD_FIELDS = frozenset((
	"fingerprint_secret_key",
	"ors_api_key",
	"abuseipdb_api_key",
	"meta_access_token",
))

EDITABLE = (
	"store_name",
	"store_logo",
	"enable_cod",
	"payment_gateway_account",
	"auto_bill_on_payment",
	"enable_advance_payment",
	"advance_payment_mode",
	"advance_payment_percent",
	"advance_payment_flat",
	"enable_raast_qr",
	"raast_iban",
	"raast_account_title",
	"raast_bank_name",
	"raast_payment_instructions",
	"cod_allowed_cities",
	"enable_pickup",
	"default_pickup_location",
	"map_embed_provider",
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
	"fingerprint_provider",
	"maps_provider",
	"gms_enabled",
	"ors_enabled",
	"gms_depth",
	"gms_concurrency",
	"geocode_cache_ttl",
	"ip_intel_enabled",
	"abuseipdb_api_key",
	"queue_schedule",
	"meta_enabled",
	"meta_catalog_id",
	"meta_access_token",
	"meta_google_product_category",
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
			"abuseipdb_api_key_set": bool(
				settings.get_password("abuseipdb_api_key", raise_exception=False)
			),
			"meta_access_token_set": bool(
				settings.get_password("meta_access_token", raise_exception=False)
			),
			"meta_last_sync": settings.meta_last_sync,
			"meta_sync_status": settings.meta_sync_status or "",
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
			"pickup_locations": [
				{
					"name": row.name,
					"location_name": row.location_name,
					"address": row.address or "",
					"google_maps_link": row.get("google_maps_link") or "",
					"latitude": row.latitude or "",
					"longitude": row.longitude or "",
					"phone": row.phone or "",
				}
				for row in (settings.get("pickup_locations") or [])
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
		elif field == "advance_payment_mode":
			value = value if value in ("Percent", "Flat") else "Percent"
		elif field == "map_embed_provider":
			value = value if value in ("OpenStreetMap", "Google Maps") else "OpenStreetMap"
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


@frappe.whitelist(methods=["POST"])
def save_pickup_locations(locations: list) -> dict:
	"""Save the pickup location table.
	Each entry: {location_name, address, google_maps_link, latitude, longitude, phone}.

	A location is placed either by a Google Maps link whose coordinates we
	parse (first choice) or by latitude/longitude entered directly in the
	editor's coordinate mode. Short Google links are resolved once, at save
	time, so checkout never fetches anything."""
	only_managers()
	from shop.storefront.pickup import (
		_valid_coords,
		is_short_gmaps_link,
		parse_gmaps_link,
		resolve_short_gmaps_link,
	)

	settings = frappe.get_doc("Shop Settings")
	settings.pickup_locations = []
	for entry in locations:
		name = (entry.get("location_name") or "").strip()
		address = (entry.get("address") or "").strip()
		if not name or not address:
			continue
		link = (entry.get("google_maps_link") or "").strip()
		coordinates = None
		if link:
			coordinates = parse_gmaps_link(link)
			if not coordinates and is_short_gmaps_link(link):
				# Google's shortener hides the coordinates — follow it once
				# and store the full URL we landed on.
				resolved = resolve_short_gmaps_link(link)
				coordinates = parse_gmaps_link(resolved)
				if coordinates:
					link = resolved
		latitude = str(entry.get("latitude") or "").strip()
		longitude = str(entry.get("longitude") or "").strip()
		if not coordinates and _valid_coords(latitude, longitude):
			# Coordinate mode: the editor sends no link, just the numbers.
			coordinates = (latitude, longitude)
		if not coordinates:
			if latitude or longitude:
				frappe.throw(
					_(
						"Latitude / longitude for {0} must be numbers within -90..90 and -180..180."
					).format(name)
				)
			frappe.throw(
				_(
					"We couldn't find coordinates in the Google Maps link for {0}. "
					"Copy the full link from Google Maps — it should contain the pin's "
					"coordinates, e.g. @29.1044,70.3298 — or enter latitude and "
					"longitude instead."
				).format(name)
			)
		settings.append(
			"pickup_locations",
			{
				"location_name": name,
				"address": address,
				"google_maps_link": link,
				"latitude": coordinates[0],
				"longitude": coordinates[1],
				"phone": (entry.get("phone") or "").strip(),
			},
		)
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


@frappe.whitelist(methods=["POST"])
def sync_meta_catalog(run_id: str | None = None) -> dict:
	"""Run a full Meta catalogue sync now: push, prune and relink.

	``run_id`` tags the progress written while this runs, so the popup can
	poll ``get_meta_sync_progress`` with the same token and ignore anything
	from an earlier run."""
	only_managers()
	from shop.integrations.meta_catalog import sync_all
	return sync_all(run_id=run_id)


@frappe.whitelist()
def get_meta_sync_progress(run_id: str | None = None) -> dict:
	"""Live step status of the Meta sync this browser started, for the popup."""
	only_managers()
	from shop.integrations.meta_catalog import progress_snapshot
	return progress_snapshot(run_id)
