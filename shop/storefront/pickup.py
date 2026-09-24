"""Store pickup: locations, map links, and checkout validation.

Pickup orders are paid like cash on delivery — collected in person when the
customer picks the order up — so no advance logic applies, and the courier
shipping charge is waived for them."""

import frappe
from frappe import _


def configured(settings=None) -> list[dict]:
	"""Pickup rows for storefronts; empty when pickup is switched off."""
	settings = settings or frappe.get_cached_doc("Shop Settings")
	if not settings.get("enable_pickup"):
		return []
	rows = []
	for row in settings.get("pickup_locations") or []:
		name = (row.location_name or "").strip()
		if not name:
			continue
		urls = map_urls(row.latitude, row.longitude, settings.get("map_embed_provider"))
		rows.append(
			{
				"name": name,
				"address": (row.address or "").strip(),
				"latitude": (row.latitude or "").strip(),
				"longitude": (row.longitude or "").strip(),
				"phone": (row.phone or "").strip(),
				"map_url": urls["map_url"],
				"directions_url": urls["directions_url"],
			}
		)
	return rows


def map_urls(latitude, longitude, provider="OpenStreetMap") -> dict:
	"""Map embed + directions links; empty strings without coordinates.

	Both embeds are keyless: OpenStreetMap's export endpoint, or Google's
	`output=embed` maps URL (no API key, no billing). The directions link
	stays Google — storefront.js swaps it for Apple Maps on iPhones."""
	lat = _coordinate(latitude)
	lng = _coordinate(longitude)
	if lat is None or lng is None:
		return {"map_url": "", "directions_url": ""}
	if (provider or "OpenStreetMap") == "Google Maps":
		map_url = f"https://maps.google.com/maps?q={lat},{lng}&hl=en&z=16&output=embed"
	else:
		# ~600m box around the pin so the embed frames the location sensibly.
		bbox = f"{lng - 0.004:.4f},{lat - 0.003:.4f},{lng + 0.004:.4f},{lat + 0.003:.4f}"
		map_url = (
			f"https://www.openstreetmap.org/export/embed.html?bbox={bbox}"
			f"&layer=mapnik&marker={lat},{lng}"
		)
	return {
		"map_url": map_url,
		"directions_url": f"https://www.google.com/maps/dir/?api=1&destination={lat},{lng}",
	}


def _coordinate(value):
	try:
		return round(float(str(value).strip()), 6)
	except (TypeError, ValueError):
		return None


def resolve(name, settings=None) -> dict:
	"""The configured location a customer chose, or a friendly throw."""
	configured_rows = configured(settings)
	wanted = (name or "").strip().lower()
	for row in configured_rows:
		if row["name"].lower() == wanted:
			return row
	frappe.throw(
		_("Choose a pickup location for your order")
		if configured_rows
		else _("Store pickup is not available")
	)
