"""Address geocoding (ORS, cached) + landmark matching for fraud scoring."""

import hashlib
import json
import math
import re

import frappe
from frappe.utils import cint, flt, get_datetime, now_datetime

GEOCODE_TTL_DAYS = 30
LANDMARK_RADIUS_KM = 3.0
LANDMARK_NAME_THRESHOLD = 72  # fuzzy ratio out of 100


def norm_text(text: str) -> str:
	"""Lowercase, collapse whitespace/punct — for hashing and fuzzy match."""
	return re.sub(r"[^a-z0-9 ]+", " ", (text or "").lower()).strip()


def address_hash(address: dict) -> str:
	"""Stable cache key from the address parts that matter."""
	parts = [
		norm_text(address.get(f) or "")
		for f in ("address_line1", "address_line2", "landmark", "city")
	]
	parts.append((address.get("pincode") or "").strip())
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


def _cache_get(hkey: str):
	row = frappe.db.get_value(
		"Shop Geocode Cache",
		{"address_hash": hkey},
		["response_json", "creation"],
		as_dict=True,
	)
	if not row:
		return None
	created = get_datetime(row.creation)
	ttl_days = GEOCODE_TTL_DAYS if "not_found" not in row.response_json else 3
	if (now_datetime() - created).days >= ttl_days:
		return None
	try:
		return json.loads(row.response_json)
	except Exception:
		return None


def _cache_set(hkey: str, summary: dict):
	existing = frappe.db.get_value("Shop Geocode Cache", {"address_hash": hkey}, "name")
	values = json.dumps(summary)
	if existing:
		frappe.db.set_value(
			"Shop Geocode Cache",
			existing,
			{"response_json": values, "latitude": summary.get("lat"), "longitude": summary.get("lng")},
			update_modified=False,
		)
	else:
		frappe.get_doc(
			{
				"doctype": "Shop Geocode Cache",
				"address_hash": hkey,
				"latitude": summary.get("lat"),
				"longitude": summary.get("lng"),
				"response_json": values,
			}
		).insert(ignore_permissions=True)


def geocode_cached(address: dict, settings_doc=None) -> dict | None:
	"""Geocode with a 30-day cache. Returns {found,lat,lng,confidence,...}
	or None when no API key / provider error. Never raises."""
	hkey = address_hash(address)
	cached = _cache_get(hkey)
	if cached is not None:
		cached["cached"] = True
		return cached

	api_key = _ors_key(settings_doc)
	if not api_key:
		return None

	full_address = ", ".join(
		p.strip()
		for p in (
			address.get("address_line1"),
			address.get("address_line2"),
			address.get("landmark"),
			address.get("city"),
			address.get("pincode"),
			"Pakistan",
		)
		if (p or "").strip()
	)
	summary = _summarize_ors(_call_ors(full_address, api_key))
	if summary is None:
		return None  # provider error: do not cache, fail open
	if not summary.get("found"):
		summary["lat"] = summary["lng"] = None
	_cache_set(hkey, summary)
	summary["cached"] = False
	return summary


def match_landmark(lat: float, lng: float, text: str, city: str | None = None, limit_radius_km: float = LANDMARK_RADIUS_KM) -> dict | None:
	"""Fuzzy-match a user-entered landmark against the local POI table.
	Returns {'name','category','city','distance_km','ratio'} of the best hit
	or None. Prefilters by bounding box, then scores name similarity."""
	text_norm = norm_text(text)
	if not text_norm or lat is None or lng is None:
		return None

	# ~1 deg = 111km; bounding box prefilter keeps candidates small
	d_lat = limit_radius_km / 110.574
	d_lng = limit_radius_km / (111.320 * max(math.cos(math.radians(lat)), 0.01))
	candidates = frappe.get_all(
		"Shop Landmark",
		filters={
			"latitude": ["between", [lat - d_lat, lat + d_lat]],
			"longitude": ["between", [lng - d_lng, lng + d_lng]],
		},
		fields=["name as landmark_name", "normalized_name", "category", "city", "latitude", "longitude"],
		limit=200,
	)

	best = None
	best_score = 0.0
	from difflib import SequenceMatcher

	for candidate in candidates:
		distance = haversine_km(lat, lng, candidate.latitude, candidate.longitude)
		if distance > limit_radius_km:
			continue
		target = candidate.normalized_name or norm_text(candidate.landmark_name)
		if not target:
			continue
		# containment bonus: entered text inside POI name or vice versa
		if text_norm in target or target in text_norm:
			ratio = 95.0
		else:
			ratio = SequenceMatcher(None, text_norm, target).ratio() * 100
		score = ratio - distance * 2.5  # closer wins ties
		if ratio < LANDMARK_NAME_THRESHOLD:
			continue
		if score > best_score:
			best_score = score
			best = {
				"name": candidate.landmark_name,
				"category": candidate.category,
				"city": candidate.city or city,
				"distance_km": round(distance, 2),
				"ratio": round(ratio, 1),
			}
	return best


def landmark_count() -> int:
	return cint(frappe.db.count("Shop Landmark"))
