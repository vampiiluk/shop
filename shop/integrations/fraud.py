import json
import re
from datetime import timedelta
from zoneinfo import ZoneInfo

import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime

FAILED_OUTCOMES = ("Failed", "RTO")

DEFAULT_PK_CITIES = [
	"karachi", "lahore", "islamabad", "rawalpindi", "faisalabad", "multan",
	"peshawar", "quetta", "sialkot", "gujranwala", "hyderabad", "bahawalpur",
	"sargodha", "abbottabad", "sukkur", "larkana", "sheikhupura",
	"rahim yar khan", "jhang", "dera ghazi khan", "gujrat", "sahiwal",
	"wah cantonment", "mardan", "kasur", "okara", "mingora", "nawabshah",
	"chiniot", "kotri", "kamoke", "hafizabad", "sadiqabad", "mirpur khas",
	"burewala", "kohat", "khanewal", "dera ismail khan", "turbat",
	"muzaffargarh", "muridke", "mandi bahauddin", "shikarpur", "jacobabad",
	"jhelum", "khanpur",
]


class FraudResult:
	def __init__(self, score: int, verdict: str, signals: dict, fp_verified: bool = False, raw_event: dict | None = None):
		self.score = score
		self.verdict = verdict
		self.signals = signals
		self.fp_verified = fp_verified
		self.raw_event = raw_event


def settings() -> frappe._dict:
	return frappe.get_cached_doc("Shop Settings")


def normalize_phone(phone) -> str:
	"""Strip spaces, dashes, +92/0 prefixes -> 10-digit number (or leftover digits)."""
	digits = re.sub(r"\D", "", str(phone or ""))
	if digits.startswith("92"):
		digits = digits[2:]
	elif digits.startswith("0"):
		digits = digits[1:]
	return digits


def canonical_cities(settings_doc=None) -> list[str]:
	"""Canonical cities from the generic address settings (falls back to the
	built-in Pakistan list while nothing is configured)."""
	settings_doc = settings_doc or settings()
	raw = getattr(settings_doc, "address_cities", None)
	if raw is None:  # field missing on very old installs
		raw = settings_doc.pk_cities
	custom = [c.strip().lower() for c in (raw or "").split(",") if c.strip()]
	return custom or DEFAULT_PK_CITIES


def home_country_codes(settings_doc=None) -> set[str]:
	"""Accepted country names/codes for the wrong-country geocode check."""
	settings_doc = settings_doc or settings()
	codes = {"pk", "pak", "pakistan"}
	extra = (getattr(settings_doc, "address_countries", None) or "").split(",")
	for entry in extra:
		token = entry.strip().lower()
		if token:
			codes.add(token)
			if len(token) > 3:
				codes.add(token[:3])
	return codes


def canonical_provinces(settings_doc=None) -> list[str]:
	"""Canonical provinces/states from the address settings."""
	settings_doc = settings_doc or settings()
	raw = getattr(settings_doc, "address_provinces", None)
	if raw:
		return [p.strip().lower() for p in raw.split(",") if p.strip()]
	return []


def _get_province_city_map(settings_doc=None) -> dict[str, list[str]]:
	"""Build province->cities mapping from the province_table (primary)
	or fall back to the hardcoded Pakistan mapping."""
	settings_doc = settings_doc or settings()
	mapping = {}
	# Try table field first
	province_table = getattr(settings_doc, "province_table", None)
	if province_table:
		for row in province_table:
			prov = (row.province_name or "").strip()
			if not prov:
				continue
			cities = [c.strip().lower() for c in (row.cities or "").split(",") if c.strip()]
			if cities:
				mapping[prov.lower()] = cities
	if mapping:
		return mapping
	# Fallback: build from address_provinces text field (legacy)
	provinces_text = getattr(settings_doc, "address_provinces", None)
	if provinces_text:
		for p in provinces_text.split(","):
			prov = p.strip()
			if prov:
				mapping[prov.lower()] = []
	return mapping


def province_for_city(city: str, settings_doc=None) -> str | None:
	"""Best-guess province for a city using the DB province_table mapping."""
	city_lower = (city or "").strip().lower()
	if not city_lower:
		return None
	mapping = _get_province_city_map(settings_doc)
	for prov, cities in mapping.items():
		if city_lower in cities:
			return prov.title()
	# Hardcoded fallback for Pakistan cities if no table configured
	if not mapping:
		_pk = {
			"lahore": "Punjab", "faisalabad": "Punjab", "rawalpindi": "Punjab",
			"multan": "Punjab", "gujranwala": "Punjab", "sialkot": "Punjab",
			"gujrat": "Punjab", "bahawalpur": "Punjab", "sargodha": "Punjab",
			"jhelum": "Punjab", "sahiwal": "Punjab", "wah cantonment": "Punjab",
			"wah cantt": "Punjab", "kasur": "Punjab", "okara": "Punjab",
			"sheikhupura": "Punjab", "jhang": "Punjab", "rahim yar khan": "Punjab",
			"dera ghazi khan": "Punjab", "mardan": "Punjab", "chiniot": "Punjab",
			"kamoke": "Punjab", "hafizabad": "Punjab", "mandi bahauddin": "Punjab",
			"toba tek singh": "Punjab", "khanewal": "Punjab", "vehari": "Punjab",
			"burewala": "Punjab", "khanpur": "Punjab", "muridke": "Punjab",
			"shikarpur": "Punjab", "nankana sahib": "Punjab",
			"karachi": "Sindh", "hyderabad": "Sindh", "sukkur": "Sindh",
			"larkana": "Sindh", "nawabshah": "Sindh", "mirpur khas": "Sindh",
			"mirpurkhas": "Sindh", "jacobabad": "Sindh", "kotri": "Sindh",
			"khairpur": "Sindh", "dadu": "Sindh", "sadiqabad": "Sindh",
			"islamabad": "Islamabad",
			"peshawar": "Khyber Pakhtunkhwa", "abbottabad": "Khyber Pakhtunkhwa",
			"kohat": "Khyber Pakhtunkhwa", "dera ismail khan": "Khyber Pakhtunkhwa",
			"mingora": "Khyber Pakhtunkhwa",
			"quetta": "Balochistan", "turbat": "Balochistan",
			"gilgit": "Gilgit-Baltistan", "skardu": "Gilgit-Baltistan",
			"mirpur": "Azad Kashmir", "muzaffarabad": "Azad Kashmir",
		}
		return _pk.get(city_lower)
	return None


def pk_hour() -> int:
	"""Current hour in Asia/Karachi."""
	return now_datetime().astimezone(ZoneInfo("Asia/Karachi")).hour


def in_risky_window(settings_doc=None) -> bool:
	settings_doc = settings_doc or settings()
	start = cint(settings_doc.fraud_risky_hour_start)
	end = cint(settings_doc.fraud_risky_hour_end)
	hour = pk_hour()
	if start < end:
		return start <= hour < end
	return hour >= start or hour < end  # window wraps midnight


def customers_for_phone(phone: str) -> list[str]:
	normalized = normalize_phone(phone)
	if not normalized:
		return []
	# Use SQL LIKE to avoid loading every Contact into Python
	contacts = frappe.db.sql(
		"""SELECT name FROM `tabContact`
		WHERE mobile_no IS NOT NULL
		AND REPLACE(REPLACE(REPLACE(REPLACE(mobile_no, ' ', ''), '-', ''), '+', ''), '(', '') LIKE %s""",
		(f"%{normalized}",),
		pluck="name",
	)
	if not contacts:
		return []
	return frappe.get_all(
		"Dynamic Link",
		filters={
			"parenttype": "Contact",
			"parent": ["in", contacts],
			"link_doctype": "Customer",
		},
		pluck="link_name",
	)


def customer_phone(customer: str) -> str:
	contact = frappe.db.get_value(
		"Dynamic Link",
		{"parenttype": "Contact", "link_doctype": "Customer", "link_name": customer},
		"parent",
	)
	if not contact:
		return ""
	return frappe.db.get_value("Contact", contact, "mobile_no") or ""


def order_stats(phone: str, email: str, since_days: int = 90) -> dict:
	"""Repeat fraud history: totals for every order tied to this phone/email."""
	now = now_datetime()
	since = now - timedelta(days=since_days)
	customers = customers_for_phone(phone)
	email_customer = None
	if email:
		email_customer = frappe.db.get_value(
			"Contact Email", {"email_id": email}, "parent"
		) and frappe.db.get_value(
			"Dynamic Link",
			{"parenttype": "Contact", "link_doctype": "Customer", "parent": frappe.db.get_value("Contact Email", {"email_id": email}, "parent")},
			"link_name",
		)
	if email_customer and email_customer not in customers:
		customers.append(email_customer)
	if not customers:
		return {"total": 0, "failed": 0, "rto": 0, "cancelled": 0}
	rows = frappe.get_all(
		"Sales Order",
		filters={"docstatus": ["in", [1, 2]], "creation": (">=", since), "customer": ["in", customers]},
		fields=["docstatus", "custom_delivery_outcome"],
	)
	return {
		"total": len(rows),
		"failed": sum(1 for r in rows if r.custom_delivery_outcome == "Failed"),
		"rto": sum(1 for r in rows if r.custom_delivery_outcome == "RTO"),
		"cancelled": sum(1 for r in rows if cint(r.docstatus) == 2),
	}


def velocity_count(phone: str, fingerprint: str, window_minutes: int = 60, as_of=None) -> tuple[int, int]:
	"""Orders in the last window from this phone and (separately) this device."""
	now = as_of or now_datetime()
	since = now - timedelta(minutes=window_minutes)
	customers = customers_for_phone(phone)
	phone_count = 0
	if customers:
		phone_count = frappe.db.count(
			"Sales Order",
			{"docstatus": ["in", [0, 1, 2]], "creation": (">=", since), "customer": ["in", customers]},
		)
	fp_count = 0
	if fingerprint:
		fp_count = frappe.db.count(
			"Sales Order",
			{"docstatus": ["in", [0, 1, 2]], "creation": (">=", since), "custom_device_fingerprint": fingerprint},
		)
	return phone_count, fp_count


def blacklist_hit(phone: str, email: str | None = None) -> dict | None:
	normalized = normalize_phone(phone)
	if not normalized and not email:
		return None
	for row in frappe.get_all("Shop Blacklist", filters={"active": 1}, fields=["name", "phone", "email", "hit_count"]):
		if normalized and normalize_phone(row.phone) == normalized:
			return row
	if email:
		email_clean = email.strip().lower()
		# Check both exact match and case-insensitive via SQL
		hit = frappe.db.get_value(
			"Shop Blacklist",
			{"active": 1, "email": email_clean},
			["name", "phone", "email", "hit_count"],
			as_dict=True,
		)
		if hit:
			return hit
		# Case-insensitive fallback
		hit = frappe.db.sql(
			"""SELECT name, phone, email, hit_count FROM `tabShop Blacklist`
			WHERE active=1 AND LOWER(email)=LOWER(%s) LIMIT 1""",
			(email_clean,),
			as_dict=True,
		)
		if hit:
			return hit[0]
	return None


def address_key(address: dict) -> str:
	parts = [
		str(address.get(f) or "").strip().lower()
		for f in ("address_line1", "address_line2", "city", "pincode")
		if (address.get(f) or "").strip()
	]
	return " | ".join(parts)


def previous_address_failed(address: dict) -> bool:
	a1 = (address.get("address_line1") or "").strip()
	city = (address.get("city") or "").strip()
	pincode = (address.get("pincode") or "").strip()
	if not a1 or not city:
		return False
	addr = frappe.db.get_value(
		"Address",
		{"address_line1": a1, "city": city, "pincode": pincode},
		"name",
	)
	if not addr:
		return False
	return bool(
		frappe.db.exists(
			"Sales Order",
			{"shipping_address_name": addr, "custom_delivery_outcome": ["in", list(FAILED_OUTCOMES)]},
		)
	)


def address_risk(address: dict, settings_doc=None, weights: dict | None = None) -> dict:
	"""Address quality: cached ORS geocode + local landmark table + heuristics.
	Returns {'score': int, 'geo': dict|None, 'landmark': dict|None, ...flags}."""
	from shop.integrations.signal_weights import get_weights as _get_weights

	w = weights or _get_weights(settings_doc)
	result = {"score": 0, "geo": None, "landmark": None}
	score = 0
	a1 = (address.get("address_line1") or "").strip()
	city = (address.get("city") or "").strip()
	pincode = (address.get("pincode") or "").strip()
	landmark = (address.get("landmark") or "").strip()
	stated_country = (address.get("country") or "").strip()
	stated_province = (address.get("state") or "").strip()

	# user-provided country mismatch (no geocode needed)
	if stated_country and stated_country.lower() not in home_country_codes(settings_doc):
		result["user_country_mismatch"] = stated_country
		score += w["user_country_mismatch"]

	# province vs city consistency check
	if stated_province:
		expected_province = province_for_city(city, settings_doc)
		if expected_province and stated_province.lower() != expected_province.lower():
			result["province_mismatch"] = stated_province
			score += w["province_mismatch"]

	# heuristics (always run)
	if len(a1) < 5:
		score += w["address_short_line1"]
	elif not re.search(r"\d", a1):
		score += w["address_no_house_number"]
	if pincode and not re.fullmatch(r"\d{5}", pincode):
		score += w["address_bad_pincode"]
	if city and city.lower() not in canonical_cities():
		score += w["address_unknown_city"]
	if not landmark:
		score += w["address_missing_landmark"]
	if previous_address_failed(address):
		score += w["address_prior_failure"]

	# geocode via cache (skips silently when no key / provider error)
	from shop.integrations.geocoding import geocode_cached, match_landmark, norm_text

	geo = geocode_cached(address, settings_doc)
	if geo is None:
		result["geo_unavailable"] = True
	elif not geo.get("found"):
		result["geo_not_found"] = True
		score += w["geo_not_found"]
	else:
		result["geo"] = {
			"label": geo.get("label"),
			"confidence": geo.get("confidence"),
			"match_type": geo.get("match_type"),
			"local_area": geo.get("local_area"),
			"admin_area": geo.get("admin_area"),
			"cached": geo.get("cached"),
		}
		country = (geo.get("country") or "").strip()
		wrong_country = country and country.lower() not in home_country_codes(settings_doc)

		if wrong_country:
			# ORS resolved the text to another country entirely: treat as not found
			result["wrong_country"] = country
			score += w["geo_wrong_country"]
		elif geo.get("match_type") == "exact" and flt(geo.get("confidence")) >= 0.8:
			score += w["geo_exact_match_bonus"]
		elif geo.get("match_type") == "fallback":
			score += w["geo_fallback_vague"]
		if not wrong_country and not geo.get("house_number"):
			score += w["geo_no_house_number"]

		# stated city vs where the address actually resolves
		geo_area = norm_text(geo.get("local_area") or geo.get("admin_area"))
		label_norm = norm_text(geo.get("label"))
		mismatch_target = geo_area or label_norm
		if not wrong_country and city and mismatch_target:
			city_norm = norm_text(city)
			if city_norm not in mismatch_target and not any(
				norm_text(c) in mismatch_target for c in canonical_cities(settings_doc) if len(c) > 3
			):
				result["city_mismatch"] = True
				score += w["geo_city_mismatch"]

		# landmark corroboration against the local POI table
		if landmark:
			match = match_landmark(geo.get("lat"), geo.get("lng"), landmark, city)
			result["landmark"] = match
			if match:
				score += w["landmark_corroborated_bonus"]
			else:
				score += w["landmark_unmatched"]

	result["score"] = max(0, min(score, 60))
	return result


def city_rto_rate(city: str) -> float:
	if not city:
		return 0
	row = frappe.db.get_value(
		"Shop City Stats", {"city": city}, ["orders_30d", "failed_30d", "rto_rate"], as_dict=True
	)
	if not row or not row.orders_30d:
		return 0
	return flt(row.rto_rate) or flt(row.failed_30d) / flt(row.orders_30d) * 100


def _fp_api_base(settings_doc=None) -> str:
	"""Server API base URL for the workspace region (us/eu/ap)."""
	region = (settings_doc or settings()).fingerprint_region or "ap"
	if region == "eu":
		return "https://eu.api.fpjs.io"
	if region == "ap":
		return "https://ap.api.fpjs.io"
	return "https://api.fpjs.io"


def verify_fingerprint(request_id: str, secret_key: str, settings_doc=None) -> dict | None:
	"""Server-side Fingerprint Identification check (their Server API v4, best effort)."""
	if not request_id or not secret_key:
		return None
	try:
		import requests

		response = requests.get(
			f"{_fp_api_base(settings_doc)}/v4/events/{request_id}",
			headers={"Authorization": f"Bearer {secret_key}"},
			timeout=3,
		)
		if response.status_code == 200:
			return response.json()
	except Exception:
		frappe.log_error(title="Fingerprint Identification verification failed")
	return None


def _camel(name: str) -> str:
	parts = name.split("_")
	return parts[0] + "".join(p.capitalize() for p in parts[1:])


def _fp_signal(identification: dict, name: str):
	"""Locate a Smart Signal across response shapes: top-level snake_case /
	camelCase, a legacy 'signals' dict, or products.smart_signals.data."""
	snake = name.strip().lower().replace("-", "_")
	keys = [snake, _camel(snake), snake.replace("_", ""), name]
	for key in keys:
		value = identification.get(key)
		if value is None:
			value = (identification.get("signals") or {}).get(key)
		if value is None:
			ss = ((identification.get("products") or {}).get("smart_signals") or {}).get("data") or {}
			value = ss.get(key)
		if isinstance(value, dict) and "result" in value:
			value = value["result"]
		if value is not None:
			return value
	return None


def _normalized_score(value) -> float:
	"""suspectScore-style metric: accept 0-100 ints or 0-1 floats."""
	try:
		v = flt(value)
	except Exception:
		return 0.0
	if v > 1:
		v = v / 100.0
	return min(max(v, 0.0), 1.0)


def evaluate_risk(
	customer: dict,
	address: dict,
	payment_method: str = "cod",
	device_fingerprint: str = "",
	fp_request_id: str = "",
	as_of=None,
) -> FraudResult:
	from shop.integrations.signal_weights import get_weights as _get_weights

	w = _get_weights()
	rto_high_pct = cint(settings().fraud_rto_high_pct) or 40
	rto_medium_pct = cint(settings().fraud_rto_medium_pct) or 20
	settings_doc = settings()
	phone = customer.get("phone") or ""
	email = (customer.get("email") or "").strip().lower()
	city = (address.get("city") or "").strip()
	signals: dict = {}
	score = 0
	fp_verified = False

	# ---- 7. device fingerprint (verified server-side via Fingerprint Identification) ----
	raw_event = None
	secret = settings_doc.get_password('fingerprint_secret_key', raise_exception=False)
	if fp_request_id and secret:
		ident = verify_fingerprint(fp_request_id, secret, settings_doc)
		fp_verified = bool(ident)
		if ident:
			raw_event = ident
			bot = _fp_signal(ident, "bot")
			tampered = bool(_fp_signal(ident, "tampering") or _fp_signal(ident, "browserTampering"))
			incognito = bool(_fp_signal(ident, "incognito"))
			privacy = bool(_fp_signal(ident, "privacy_settings"))
			replayed = bool(_fp_signal(ident, "replayed"))
			suspect = _normalized_score(_fp_signal(ident, "suspect_score") or _fp_signal(ident, "suspectScore"))
			proxy = bool(_fp_signal(ident, "proxy"))
			vpn = bool(_fp_signal(ident, "vpn"))
			vm = bool(_fp_signal(ident, "virtual_machine"))
			blocklist = _fp_signal(ident, "ip_blocklist") or {}
			ipinfo = (_fp_signal(ident, "ip_info") or {}).get("v4") or {}
			geo = ipinfo.get("geolocation") or {}

			signals["fp_suspect_score"] = suspect
			signals["fp_bot"] = bot
			signals["fp_tampered"] = tampered
			signals["fp_incognito"] = incognito
			signals["fp_replayed"] = replayed
			signals["fp_visitor_id"] = (ident.get("identification") or {}).get("visitor_id")
			signals["fp_proxy"] = proxy
			signals["fp_vpn"] = vpn
			signals["fp_virtual_machine"] = vm
			signals["fp_ip_blocklist"] = blocklist
			signals["fp_network"] = {
				"ip": ipinfo.get("address"),
				"city": geo.get("city_name"),
				"country": geo.get("country_name"),
				"isp": ipinfo.get("asn_name"),
				"datacenter": bool(ipinfo.get("datacenter_result")),
			}

			if bot in ("bad", "all") or tampered or replayed:
				score += w["fp_bot_tamper_replay"]
			elif suspect >= 0.8:
				score += w["fp_suspect_high"]
			elif suspect >= 0.5:
				score += w["fp_suspect_medium"]
			if blocklist.get("attack_source") or blocklist.get("tor_node") or blocklist.get("email_spam"):
				score += w["ip_blocklist_hit"]
			if proxy:
				score += w["proxy_detected"]
			if incognito or privacy:
				score += w["incognito_privacy"]
		else:
			# request id sent but verification failed -> tampered/replayed id
			signals["fp_verify_failed"] = True
			score += w["fp_verify_failed"]
	elif payment_method == "cod" and not device_fingerprint:
		score += w["missing_fingerprint"]
		signals["missing_fingerprint"] = True

	# ---- 1. repeat fraud history ----
	stats = order_stats(phone, email)
	signals["repeat_history"] = stats
	failed_rto = stats["failed"] + stats["rto"]
	if failed_rto:
		score += min(failed_rto * w["history_failed_rto_per"], w["history_failed_rto_cap"])
	if stats["total"] and flt(stats["cancelled"]) / stats["total"] > 0.5:
		score += w["history_cancelled_ratio_pts"]
		signals["history_cancelled"] = True

	# ---- 2. phone blacklist ----
	hit = blacklist_hit(phone, email)
	if hit:
		signals["blacklisted"] = hit.name
		score += w["blacklist_hit"]

	# ---- 3. address risk ----
	addr = address_risk(address, settings_doc, weights=w)
	addr_risk = addr["score"]
	signals["address_score"] = addr_risk
	if addr.get("geo_not_found"):
		signals["address_geo_not_found"] = True
	if addr.get("city_mismatch"):
		signals["address_city_mismatch"] = True
	if addr.get("user_country_mismatch"):
		signals["address_country_mismatch"] = addr["user_country_mismatch"]
	if addr.get("province_mismatch"):
		signals["address_province_mismatch"] = addr["province_mismatch"]
	if addr.get("wrong_country"):
		signals["address_wrong_country"] = addr["wrong_country"]
	signals["address_landmark_match"] = addr.get("landmark")
	score += addr_risk

	# ---- 4. order velocity ----
	orders_1hr, fp_1hr = velocity_count(phone, device_fingerprint, 60, as_of=as_of)
	signals["orders_last_60m"] = orders_1hr
	signals["fp_orders_last_60m"] = fp_1hr
	max_per_hour = cint(settings_doc.fraud_velocity_max)
	if max_per_hour and orders_1hr >= max_per_hour:
		signals["velocity_block"] = True
		score += w["velocity_block"]
	elif orders_1hr > 1:
		score += min((orders_1hr - 1) * w["velocity_extra_per_order"], w["velocity_extra_cap"])
	if device_fingerprint and fp_1hr > orders_1hr:
		signals["fp_multiple_phones"] = True
		score += w["fp_multiple_phones"]

	# ---- 5. city RTO rate ----
	rate = city_rto_rate(city)
	signals["city_rto_rate"] = rate
	if rate >= rto_high_pct:
		score += w["city_rto_high"]
	elif rate >= rto_medium_pct:
		score += w["city_rto_medium"]

	# ---- 6. time-of-day pattern ----
	if payment_method == "cod" and in_risky_window(settings_doc):
		signals["risky_hour"] = True
		score += w["risky_hour"]

	score = min(score, 100)
	if hit and (payment_method == "cod" or cint(settings_doc.fraud_blacklist_blocks_all)):
		verdict = "Block"
	elif signals.get("velocity_block") and payment_method == "cod":
		verdict = "Block"
	elif score >= cint(settings_doc.fraud_advance_threshold) and payment_method == "cod":
		verdict = "Advance Required"
	elif score >= 40:
		verdict = "Flag"
	else:
		verdict = "Pass"
	# Increment blacklist hit count after scoring is complete (avoids write lock during read)
	if hit:
		frappe.db.set_value("Shop Blacklist", hit.name, "hit_count", cint(hit.hit_count) + 1)
	return FraudResult(score, verdict, signals, fp_verified, raw_event)


def log_fraud_event(order: str | None, customer: dict, address: dict, payment_method: str, fingerprint: str, result: FraudResult):
	if result.verdict == "Pass":
		return
	frappe.get_doc(
		{
			"doctype": "Shop Fraud Event",
			"order": order,
			"phone": customer.get("phone"),
			"email": customer.get("email"),
			"city": address.get("city"),
			"payment_method": payment_method,
			"device_fingerprint": fingerprint,
			"fp_verified": 1 if result.fp_verified else 0,
			"signals": json.dumps(result.signals),
			"score": result.score,
			"verdict": result.verdict,
		}
	).insert(ignore_permissions=True)


def stamp_order(order: str, fingerprint: str, fp_request_id: str, result: FraudResult):
	values = {
		"custom_device_fingerprint": fingerprint or None,
		"custom_fp_request_id": fp_request_id or None,
		"custom_fraud_score": result.score,
		"custom_fraud_signals": json.dumps(result.signals),
		"custom_fraud_verdict": result.verdict,
	}
	if getattr(result, "raw_event", None):
		values["custom_fp_event"] = json.dumps(result.raw_event)
	frappe.db.set_value("Sales Order", order, values)


def add_to_blacklist(phone: str, reason: str, source: str = "Manual", email: str | None = None):
	if not normalize_phone(phone) and not email:
		return None
	existing = blacklist_hit(phone, email)
	if existing:
		return existing.name
	doc = frappe.get_doc(
		{
			"doctype": "Shop Blacklist",
			"phone": phone or "",
			"email": email,
			"reason": reason,
			"source": source,
			"active": 1,
		}
	).insert(ignore_permissions=True)
	return doc.name


def update_city_stats(city: str):
	"""Recompute the 30-day RTO picture for one city from the orders table."""
	if not city:
		return
	since = now_datetime() - timedelta(days=30)
	orders = frappe.db.sql(
		"""
		SELECT COUNT(*) FROM `tabSales Order` so
		JOIN `tabAddress` a ON a.name = so.shipping_address_name
		WHERE so.docstatus = 1 AND a.city = %s AND so.creation >= %s
		""",
		(city, since),
	)[0][0]
	failed = frappe.db.sql(
		"""
		SELECT COUNT(*) FROM `tabSales Order` so
		JOIN `tabAddress` a ON a.name = so.shipping_address_name
		WHERE so.docstatus = 1 AND a.city = %s AND so.creation >= %s
		AND so.custom_delivery_outcome IN ('Failed', 'RTO')
		""",
		(city, since),
	)[0][0]
	rate = flt(failed) / orders * 100 if orders else 0
	existing = frappe.db.get_value("Shop City Stats", {"city": city})
	if existing:
		frappe.db.set_value(
			"Shop City Stats",
			existing,
			{"orders_30d": orders, "failed_30d": failed, "rto_rate": rate},
		)
	else:
		frappe.get_doc(
			{
				"doctype": "Shop City Stats",
				"city": city,
				"orders_30d": orders,
				"failed_30d": failed,
				"rto_rate": rate,
			}
		).insert(ignore_permissions=True)


def record_delivery_outcome(order: str, outcome: str):
	"""Feedback loop: record a delivery result, learn city RTO stats and auto-blacklist."""
	if outcome not in ("Delivered", "Failed", "RTO"):
		frappe.throw(_("Outcome must be Delivered, Failed or RTO"))
	so = frappe.get_doc("Sales Order", order)
	if so.custom_delivery_outcome and so.custom_delivery_outcome != "Pending":
		frappe.throw(_("Delivery outcome already recorded as {0}").format(so.custom_delivery_outcome))
	city = frappe.db.get_value("Address", so.shipping_address_name, "city") or ""
	so.db_set("custom_delivery_outcome", outcome)
	if outcome in FAILED_OUTCOMES:
		phone = customer_phone(so.customer)
		failures = cint(frappe.db.get_value("Customer", so.customer, "custom_failed_deliveries")) + 1
		frappe.db.set_value("Customer", so.customer, "custom_failed_deliveries", failures)
		threshold = cint(settings().fraud_auto_blacklist_failures)
		if threshold and failures >= threshold:
			add_to_blacklist(
				phone,
				reason=_("Auto: {0} failed/RTO deliveries").format(failures),
				source="Auto",
				email=frappe.db.get_value("Customer", so.customer, "email_id"),
			)
	update_city_stats(city)
	frappe.db.commit()
	return {"order": order, "outcome": outcome}