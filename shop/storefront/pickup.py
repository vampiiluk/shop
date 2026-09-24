"""Store pickup: locations, map links, and checkout validation.

Pickup orders are paid like cash on delivery — collected in person when the
customer picks the order up — so no advance logic applies, and the courier
shipping charge is waived for them."""

import re
from urllib.parse import unquote

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
		latitude = (row.latitude or "").strip()
		longitude = (row.longitude or "").strip()
		if not latitude or not longitude:
			# Rows saved from the Google Maps link editor carry the link only
			# until the save path parses it; derive the coordinates here so a
			# link-only row still renders a map.
			parsed = parse_gmaps_link(row.get("google_maps_link") or "")
			if parsed:
				latitude, longitude = parsed
		urls = map_urls(latitude, longitude, settings.get("map_embed_provider"))
		rows.append(
			{
				"name": name,
				"address": (row.address or "").strip(),
				"latitude": latitude,
				"longitude": longitude,
				"phone": (row.phone or "").strip(),
				"map_url": urls["map_url"],
				"directions_url": urls["directions_url"],
			}
		)
	return rows


_GMAPS_QUERY_COORDS = re.compile(
	r"[?&](?:q|query|ll|center|origin|destination|daddr)=(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)"
)
_GMAPS_DATA_COORDS = re.compile(r"!3d(-?\d+(?:\.\d+)?)!4d(-?\d+(?:\.\d+)?)")
_GMAPS_AT_COORDS = re.compile(r"@(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)")
_GMAPS_ANY_PAIR = re.compile(r"(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)")

# Only Google's own shorteners are resolved over the network at save time.
_SHORT_LINK_HOSTS = ("maps.app.goo.gl", "goo.gl", "g.co")


def parse_gmaps_link(link) -> tuple[str, str] | None:
	"""Latitude/longitude captured from a Google Maps link, else None.

	Handles the shapes Google actually hands out: ``@lat,lng`` viewports,
	``!3dlat!4dlng`` pins, coordinate query parameters, and (as a last
	resort) any ``lat,lng`` pair in the URL. Returns the captured coordinate
	strings so they round-trip exactly as Google wrote them."""
	if not link:
		return None
	link = unquote(str(link).strip())
	for pattern in (_GMAPS_QUERY_COORDS, _GMAPS_DATA_COORDS, _GMAPS_AT_COORDS, _GMAPS_ANY_PAIR):
		match = pattern.search(link)
		if not match:
			continue
		if _valid_coords(match.group(1), match.group(2)):
			return match.group(1), match.group(2)
	return None


def is_short_gmaps_link(link) -> bool:
	"""True for Google's URL shorteners, the only hosts we fetch."""
	if not link:
		return False
	host = re.sub(r"^[a-z]+://", "", str(link).strip().lower()).split("/", 1)[0].split("?", 1)[0]
	host = host.rsplit("@", 1)[-1].split(":", 1)[0]
	return any(host == short or host.endswith("." + short) for short in _SHORT_LINK_HOSTS)


def resolve_short_gmaps_link(link) -> str:
	"""Follow a Google short link to its full URL; '' on any failure.

	The request is scoped to Google's shortener hosts, redirects are capped,
	and the final URL must still resolve to a Google host — so a hostile link
	can never make the server fetch, or store, an arbitrary address."""
	if not is_short_gmaps_link(link):
		return ""
	try:
		import requests

		session = requests.Session()
		session.max_redirects = 5
		with session.get(link, allow_redirects=True, stream=True, timeout=(3.05, 6)) as response:
			resolved = str(response.url or "")
	except Exception:
		return ""
	return resolved if _is_google_host(resolved) else ""


def _is_google_host(link) -> bool:
	"""True when the URL's host is Google-owned (google.com and its ccTLDs,
	goo.gl, g.co). Rejects look-alikes such as google.evil.com."""
	host = re.sub(r"^[a-z]+://", "", str(link).strip().lower()).split("/", 1)[0].split("?", 1)[0]
	host = host.rsplit("@", 1)[-1].split(":", 1)[0]
	return bool(
		re.fullmatch(r"(?:[a-z0-9-]+\.)*google\.(?:[a-z]{2,3}\.)?[a-z]{2,3}", host)
		or re.fullmatch(r"(?:[a-z0-9-]+\.)*(?:goo\.gl|g\.co)", host)
	)


def _valid_coords(latitude: str, longitude: str) -> bool:
	try:
		return -90 <= float(latitude) <= 90 and -180 <= float(longitude) <= 180
	except (TypeError, ValueError):
		return False


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
