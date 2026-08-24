"""Address geocoding helpers.

ORS geocoding writes are handled exclusively by `shop.integrations.verification.run_ors_verification`.
Reads go through `get_or_create_verification` (verification module).
This module only provides helper functions: address_hash, norm_text, haversine_km,
and the low-level ORS API wrappers used by the verification module.
"""

import hashlib
import math
import re

import frappe
from frappe.utils import flt

GEOCODE_TTL_DAYS = 30


def norm_text(text: str) -> str:
	"""Lowercase, collapse whitespace/punct — for hashing and fuzzy match."""
	return re.sub(r"[^a-z0-9 ]+", " ", (text or "").lower()).strip()


def address_hash(address: dict) -> str:
	"""Stable cache key from the full address line INCLUDING the nearest landmark.

	The landmark is part of the address identity: one verification record per
	unique street address + landmark combination. Changing the landmark produces
	a new hash and therefore a fresh verification.
	Accepts both key conventions: 'address_line1' (checkout/verification)
	and 'line1' (tools._get_order_address)."""

	def _g(*keys: str) -> str:
		for k in keys:
			v = address.get(k)
			if v:
				return str(v)
		return ""

	parts = [
		norm_text(_g("address_line1", "line1")),
		norm_text(_g("address_line2", "line2")),
		norm_text(_g("city")),
	]
	parts.append((address.get("pincode") or "").strip())
	parts.append(norm_text(_g("landmark", "custom_landmark")))
	return hashlib.md5("|".join(parts).encode()).hexdigest()


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
	radius = 6371.0
	p1, p2 = math.radians(lat1), math.radians(lat2)
	dp = p2 - p1
	dl = math.radians(lon2 - lon1)
	a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
	return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _ors_key(settings_doc=None) -> str:
	settings_doc = settings_doc or frappe.get_cached_doc("Shop Settings")
	return settings_doc.get_password("ors_api_key", raise_exception=False) or ""


def _call_ors(full_address: str, api_key: str) -> dict | None:
	try:
		import requests
		import urllib.parse

		url = (
			"https://api.openrouteservice.org/geocode/search"
			f"?api_key={api_key}&text={urllib.parse.quote(full_address)}"
		)
		response = requests.get(url, timeout=4)
		if response.status_code != 200:
			return None
		return response.json()
	except Exception:
		return None


def _summarize_ors(payload: dict | None) -> dict | None:
	"""Reduce an ORS response to the fields we score on."""
	if not payload:
		return None
	features = payload.get("features") or []
	if not features:
		return {"found": False}
	props = features[0].get("properties") or {}
	geometry = (features[0].get("geometry") or {}).get("coordinates") or [None, None]
	label = props.get("label") or ""
	admin_area = ""
	local_area = ""
	for area in props.get("admin_area_levels") or []:
		level = area.get("level")
		name = area.get("name") or ""
		if level == 7:
			local_area = name
		elif level == 6 and not admin_area:
			admin_area = name
	house_number = bool(props.get("street")) or bool(re.search(r"\d", label))
	return {
		"found": True,
		"lat": geometry[1],
		"lng": geometry[0],
		"confidence": flt(props.get("confidence")),
		"match_type": props.get("match_type") or "",
		"label": label[:255],
		"local_area": local_area,
		"admin_area": admin_area,
		"country": props.get("country") or "",
		"house_number": house_number,
	}
