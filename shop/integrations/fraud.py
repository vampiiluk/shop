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
	"""Canonical cities from the province table (primary) or the generic field."""
	settings_doc = settings_doc or settings()
	# The province table drives the checkout dropdowns; prefer it when configured
	# so a stale generic city list cannot shadow what the merchant actually set up.
	seen = set()
	cities = []
	for row in (getattr(settings_doc, "province_table", None) or []):
		for c in (getattr(row, "cities", None) or "").split(","):
			c = c.strip().lower()
			if c and c not in seen:
				seen.add(c)
				cities.append(c)
	if cities:
		return cities
	raw = getattr(settings_doc, "address_cities", None)
	if raw is None:  # field missing on very old installs
		raw = getattr(settings_doc, "pk_cities", None)
	return [c.strip().lower() for c in (raw or "").split(",") if c.strip()]


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
	# Fall back to province_table entries
	provinces = []
	for row in (getattr(settings_doc, "province_table", None) or []):
		name = (getattr(row, "province_name", None) or "").strip()
		if name:
			provinces.append(name.lower())
	return provinces


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


# --- scoring-model constants ---------------------------------------------
# The old velocity control counted orders in the last 60 minutes, so a
# customer ordering once an hour was never "fast" and the cap never applied.
# Velocity is now a decaying count over a full day: an order counts fully for
# its first hour, then loses half its weight every VELOCITY_HALF_LIFE_HOURS.
VELOCITY_WINDOW_HOURS = 24
VELOCITY_HALF_LIFE_HOURS = 6.0
# fraud_velocity_max used to mean "orders per hour". It now means "orders per
# day", multiplied before it blocks: two or three orders in a day is normal for
# this store, and blocking that would cost more than the abuse it stops.
VELOCITY_BLOCK_MULTIPLIER = 3
# One input class must not own the score. The address model reaches 80 on its
# own, entirely from text the customer typed, so its contribution to the order
# score is capped here; the raw 0-80 scale stays on the verification record.
ADDRESS_SCORE_CAP = 35
# A Block on the total score, allowed only when at least one signal was
# actually verified - otherwise the score is built from the customer's typing.
BLOCK_SCORE_THRESHOLD = 92
# Correlation needs enough digits to mean something. Below this a claim is not
# evidence of anything, and matching it against every contact invents history.
MIN_PHONE_DIGITS_FOR_CORRELATION = 7
# Hard ceiling on the customer list fed into history lookups, so a fuzzy match
# cannot turn into a runaway IN (...) list.
MAX_CORRELATED_CUSTOMERS = 50
# Address-level ordering: the signal that survives identity rotation, because
# the address is not what a fraudster changes for free.
ADDRESS_VELOCITY_WINDOW_HOURS = 24
ADDRESS_VELOCITY_CUSTOMERS = 3
# Re-evaluating every order that ever shared one address in a single pass is
# what exhausted the free IP-intel quotas; the rest waits for the next pass.
MAX_REEVALUATE_PER_RUN = 50


def decay_factor(age_hours: float) -> float:
	"""Weight of an order that happened `age_hours` ago (1.0 -> 0.5 -> 0.25)."""
	if age_hours <= 0:
		return 1.0
	return 0.5 ** (age_hours / VELOCITY_HALF_LIFE_HOURS)


def normalize_city(city: str | None) -> str:
	"""One key per place: case, padding and inner spacing collapsed.

	City stats are looked up by whatever the customer typed, so "Rahimyar Yar
	Khan" and "Rahim Yar Khan" were two rows with two rates and half the
	lookups missed.
	"""
	return " ".join(str(city or "").split()).lower()


def _velocity_clauses(phone: str, fingerprint: str, address: dict) -> tuple[list[str], list[str]]:
	"""OR-clauses matching anything this order can be recognised by."""
	clauses: list[str] = []
	values: list = []
	customers = customers_for_phone(phone)
	if customers:
		clauses.append("`customer` in %s")
		values.append(tuple(customers))
	if fingerprint:
		clauses.append("`custom_device_fingerprint` = %s")
		values.append(fingerprint)
	from shop.integrations.geocoding import address_hash

	hkey = address_hash(address)
	clauses.append("`custom_address_hash` = %s")
	values.append(hkey)
	return clauses, values, hkey


def velocity_profile(
	phone: str,
	fingerprint: str,
	address: dict,
	as_of=None,
	exclude_order: str = "",
) -> dict:
	"""Order pressure over the last day, decaying, across phone, device and
	address together - so a customer cannot walk past the cap simply by waiting
	an hour, and rotating the phone no longer resets the picture.
	"""
	now = as_of or now_datetime()
	since = now - timedelta(hours=VELOCITY_WINDOW_HOURS)
	clauses, values, hkey = _velocity_clauses(phone, fingerprint, address)
	not_self = " and `name` != %s" if exclude_order else ""
	sql = f"""
		SELECT `name`, `creation`, `custom_address_hash`
		FROM `tabSales Order`
		WHERE ({' or '.join(clauses)}) and `docstatus` in (0, 1, 2)
		{not_self} and `creation` >= %s
	"""
	rows = frappe.db.sql(
		sql, tuple(values) + ((exclude_order,) if exclude_order else ()) + (since,), as_dict=True
	)
	decayed = 0.0
	by_address = 0
	last_hour = 0
	for row in rows:
		age = (now - row.creation).total_seconds() / 3600.0
		decayed += decay_factor(age)
		if age <= 1:
			last_hour += 1
		if row.custom_address_hash == hkey:
			by_address += 1
	return {
		"orders_24h": len(rows),
		"decayed": round(decayed, 2),
		"by_address_24h": by_address,
		# Kept for the admin panel, which has always shown the last hour; the
		# score itself uses the decayed day count above.
		"last_hour": last_hour,
	}


def address_activity(address: dict, exclude_order: str = "") -> dict:
	"""How busy one address is, how many different customers used it, and how
	many of its deliveries have already failed.
	"""
	line1 = (address.get("address_line1") or "").strip()
	city = (address.get("city") or "").strip()
	pincode = (address.get("pincode") or "").strip()
	if not line1 or not city:
		return {"orders_24h": 0, "customers_24h": 0, "failures": 0}
	since = now_datetime() - timedelta(hours=ADDRESS_VELOCITY_WINDOW_HOURS)
	rows = frappe.db.sql(
		"""
		SELECT so.name, so.customer, so.creation, so.custom_delivery_outcome
		FROM `tabSales Order` so
		JOIN `tabAddress` a ON a.name = so.shipping_address_name
		WHERE so.docstatus in (1, 2)
		  AND a.address_line1 = %s AND a.city = %s AND a.pincode = %s
		"""
		+ (" AND so.name != %s" if exclude_order else "")
		+ " ORDER BY so.creation DESC LIMIT 200",
		((line1, city, pincode) + ((exclude_order,) if exclude_order else ())),
		as_dict=True,
	)
	recent = [r for r in rows if r.creation >= since]
	return {
		"orders_24h": len(recent),
		"customers_24h": len({r.customer for r in recent}),
		"failures": sum(1 for r in rows if (r.custom_delivery_outcome or "") in FAILED_OUTCOMES),
	}


def identity_trust(phone: str, fingerprint: str, fp_verified: bool = False, ip_flagged: bool = False) -> dict:
	"""How much of this order's identity the server can stand behind.

	`unverified` means every identifier is a self-declared value: the phone
	matches no contact, the device was never identified server-side, and the IP
	carries no reputation. That is not proof of fraud - it is the reason a clean
	lookup must never be read as a known-good customer.
	"""
	known_phone = bool(customers_for_phone(phone))
	known_device = False
	if fingerprint:
		known_device = bool(
			frappe.db.exists(
				"Sales Order",
				{
					"custom_device_fingerprint": fingerprint,
					"custom_fraud_signals": ["like", "%fp_visitor_id%"],
				},
			)
		)
	return {
		"known_phone": known_phone,
		"known_device": known_device,
		"unverified": not (known_phone or known_device or fp_verified or ip_flagged),
	}


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
	"""Customers reachable from a claimed phone number.

	Two corrections over the previous contains-match. A claim shorter than
	MIN_PHONE_DIGITS_FOR_CORRELATION is not evidence of anything: "0300" used
	to match every contact whose number contained those digits, which handed
	the order somebody else's delivery history and a customer list large
	enough to slow checkout down. The SQL pattern is now only a pre-filter -
	every candidate is re-checked against its own normalised number, so a
	longer number that merely contains the claim no longer counts - and the
	list is capped so one fuzzy hit cannot become a runaway IN (...) clause.
	"""
	normalized = normalize_phone(phone)
	if len(normalized) < MIN_PHONE_DIGITS_FOR_CORRELATION:
		return []
	candidates = frappe.db.sql(
		"""SELECT name, mobile_no FROM `tabContact`
		WHERE mobile_no IS NOT NULL
		AND REPLACE(REPLACE(REPLACE(REPLACE(mobile_no, ' ', ''), '-', ''), '+', ''), '(', '') LIKE %s
		LIMIT 500""",
		(f"%{normalized}%",),
		as_dict=True,
	)
	exact = [row.name for row in candidates if normalize_phone(row.mobile_no) == normalized]
	if not exact:
		return []
	customers = frappe.get_all(
		"Dynamic Link",
		filters={
			"parenttype": "Contact",
			"parent": ["in", exact],
			"link_doctype": "Customer",
		},
		pluck="link_name",
	)
	seen: set[str] = set()
	unique: list[str] = []
	for customer in customers or []:
		if customer not in seen:
			seen.add(customer)
			unique.append(customer)
	return unique[:MAX_CORRELATED_CUSTOMERS]


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


# Blacklist lookup: the stored number is normalised in SQL, because the stored
# side is written by a human in whatever format they type. Stripping only
# spaces and dashes was not enough - the comparison has to agree with
# normalize_phone() on the stored value as well as on the claim, or the one
# control that can refuse an order silently stops matching: "03001234567",
# "+92 300 1234567" and "0300-1234567" are the same number, and the denylist
# has to know it.
_BLACKLIST_PHONE_SQL = "REGEXP_REPLACE(COALESCE(phone, ''), '[^0-9]', '')"
_BLACKLIST_FIELDS = "name, phone, email, hit_count"


def _blacklist_phone_variants(phone: str) -> list[str]:
	"""Every spelling of one number that a blacklist row may hold.

	Accepts any spelling rather than assuming the caller already normalised:
	normalize_phone() reduces a number to bare national digits by dropping a 92
	or a leading 0, so a stored value can still carry either prefix, and a
	caller that forgets to normalise first would quietly match nothing.
	"""
	normalized = normalize_phone(phone)
	if not normalized:
		return []
	variants = {normalized, "0" + normalized, "92" + normalized}
	return sorted(variants)


def blacklist_hit(phone: str, email: str | None = None) -> dict | None:
	"""Active blacklist entry for this phone or email, or None.

	One query rather than a loop over every active row, but the same answer the
	Python comparison gave: both sides are reduced to bare digits and the 0/92
	prefix variants are matched too.
	"""
	normalized = normalize_phone(phone)
	email_clean = (email or "").strip()
	if len(normalized) < MIN_PHONE_DIGITS_FOR_CORRELATION and not email_clean:
		return None
	clauses: list[str] = []
	values: list = []
	if len(normalized) >= MIN_PHONE_DIGITS_FOR_CORRELATION:
		clauses.append(f"({_BLACKLIST_PHONE_SQL}) in %s")
		values.append(tuple(_blacklist_phone_variants(normalized)))
	if email_clean:
		clauses.append("LOWER(email) = LOWER(%s)")
		values.append(email_clean)
	if not clauses:
		return None
	rows = frappe.db.sql(
		f"SELECT {_BLACKLIST_FIELDS} FROM `tabShop Blacklist` "
		f"WHERE active = 1 AND ({' OR '.join(clauses)}) ORDER BY creation DESC LIMIT 1",
		tuple(values),
		as_dict=True,
	)
	return rows[0] if rows else None


def record_blacklist_hit(name: str) -> None:
	"""Count a blacklist hit atomically, once per scoring run.

	The old read-then-write lost updates when two orders landed together, and
	the placement path counted a single order up to three times (placement,
	background evaluation, verification re-evaluation), overstating the evidence
	a manager reads beside the reason.
	"""
	frappe.db.sql(
		"UPDATE `tabShop Blacklist` SET hit_count = COALESCE(hit_count, 0) + 1 WHERE name = %s", name
	)


def address_key(address: dict) -> str:
	parts = [
		str(address.get(f) or "").strip().lower()
		for f in ("address_line1", "address_line2", "city", "pincode")
		if (address.get(f) or "").strip()
	]
	return " | ".join(parts)


def address_failure_count(address: dict) -> int:
	"""How many deliveries have already failed at this address.

	A count rather than a yes/no: one failed parcel is a bad day, six is a
	drop point, and the weight should be able to say so. Compared against the
	Address rows directly, so it does not depend on which customer's record the
	address happens to be linked to.
	"""
	a1 = (address.get("address_line1") or "").strip()
	city = (address.get("city") or "").strip()
	pincode = (address.get("pincode") or "").strip()
	if not a1 or not city:
		return 0
	return cint(
		frappe.db.sql(
			"""
			SELECT COUNT(*)
			FROM `tabSales Order` so
			JOIN `tabAddress` a ON a.name = so.shipping_address_name
			WHERE so.docstatus in (1, 2)
			  AND a.address_line1 = %s AND a.city = %s AND a.pincode = %s
			  AND so.custom_delivery_outcome IN %s
			""",
			(a1, city, pincode, tuple(FAILED_OUTCOMES)),
		)[0][0]
	)


def previous_address_failed(address: dict) -> bool:
	"""Kept for callers that want the boolean; the score itself wants the count."""
	return address_failure_count(address) > 0


def compute_verification_risk(
	address: dict,
	ors_result: dict | None = None,
	gms_results: list | None = None,
	settings_doc=None,
	weights: dict | None = None,
) -> dict:
	"""Compute the combined address verification score (0-80).

	One score per unique address+landmark: location accuracy (heuristics + ORS
	geocoding) plus landmark validity (landmark text found in GMS results).
	Returns {'score': int, 'status': 'Complete'|'Partial', 'details': dict}.
	"""
	from shop.integrations.geocoding import norm_text, haversine_km

	w = weights or _get_weights(settings_doc)
	result = {"geo": None, "gms": None, "gms_landmark": None}
	score = 0
	a1 = (address.get("address_line1") or address.get("line1") or "").strip()
	city = (address.get("city") or "").strip()
	pincode = (address.get("pincode") or "").strip()
	stated_country = (address.get("country") or "").strip()
	stated_province = (address.get("state") or address.get("province") or "").strip()

	# --- Heuristics ---
	if stated_country and stated_country.lower() not in _home_country_codes(settings_doc):
		result["user_country_mismatch"] = stated_country
		score += w["user_country_mismatch"]

	if stated_province:
		expected = _province_for_city(city, settings_doc)
		if expected and stated_province.lower() != expected.lower():
			result["province_mismatch"] = stated_province
			score += w["province_mismatch"]

	if len(a1) < 5:
		score += w["address_short_line1"]
	elif not re.search(r"\d", a1):
		score += w["address_no_house_number"]
	if pincode and not re.fullmatch(r"\d{5}", pincode):
		score += w["address_bad_pincode"]
	if city and city.lower() not in _canonical_cities():
		score += w["address_unknown_city"]
	failures = address_failure_count(address)
	if failures:
		result["address_prior_failures"] = failures
		score += min(failures * w["address_prior_failure_per"], w["address_prior_failure_cap"])

	# --- ORS signals ---
	if ors_result and ors_result.get("found"):
		result["geo"] = {
			"label": ors_result.get("label"),
			"confidence": ors_result.get("confidence"),
			"match_type": ors_result.get("match_type"),
			"local_area": ors_result.get("local_area"),
			"admin_area": ors_result.get("admin_area"),
		}
		country = (ors_result.get("country") or "").strip()
		wrong_country = country and country.lower() not in _home_country_codes(settings_doc)

		if wrong_country:
			result["wrong_country"] = country
			score += w["geo_wrong_country"]
		elif ors_result.get("match_type") == "exact" and flt(ors_result.get("confidence")) >= 0.8:
			score += w["geo_exact_match_bonus"]
		elif ors_result.get("match_type") == "fallback":
			score += w["geo_fallback_vague"]
		if not wrong_country and not ors_result.get("house_number"):
			score += w["geo_no_house_number"]

		geo_area = norm_text(ors_result.get("local_area") or ors_result.get("admin_area"))
		label_norm = norm_text(ors_result.get("label"))
		mismatch_target = geo_area or label_norm
		if not wrong_country and city and mismatch_target:
			city_norm = norm_text(city)
			if city_norm not in mismatch_target and not any(
				norm_text(c) in mismatch_target for c in _canonical_cities(settings_doc) if len(c) > 3
			):
				result["city_mismatch"] = True
				score += w["geo_city_mismatch"]
	elif ors_result is not None:
		result["geo_not_found"] = True
		score += w["geo_not_found"]
	else:
		result["geo_unavailable"] = True

	# --- GMS signals ---
	gms_count = len(gms_results) if isinstance(gms_results, list) else 0

	if gms_results is not None:
		gms_info = {"result_count": gms_count}

		if gms_count == 0:
			score += w["gms_no_results"]
			gms_info["no_results"] = True
		else:
			score += w["gms_results_bonus"]
			gms_info["has_results"] = True

			ors_lat = ors_result.get("lat") if ors_result else None
			ors_lng = ors_result.get("lng") if ors_result else None
			if ors_lat and ors_lng and gms_results:
				first = gms_results[0] if isinstance(gms_results[0], dict) else {}
				gms_lat = first.get("lat")
				gms_lng = first.get("lng")
				if gms_lat and gms_lng:
					try:
						dist = haversine_km(float(ors_lat), float(ors_lng), float(gms_lat), float(gms_lng))
						gms_info["distance_km"] = round(dist, 2)
						if dist > 5.0:
							score += w["gms_coords_mismatch_ors"]
							gms_info["coords_mismatch"] = True
					except (ValueError, TypeError):
						pass

			categories = set()
			for r in gms_results:
				if isinstance(r, dict) and r.get("category"):
					categories.add(r["category"].lower())
			if gms_count > 0 and not categories:
				score += w["gms_residential_area"]
				gms_info["no_business_categories"] = True

			gms_info["categories"] = list(categories)[:5]

		result["gms"] = gms_info

	# --- Landmark validation (part of the address; checked against GMS results) ---
	landmark = (address.get("landmark") or "").strip()
	if not landmark:
		score += w["address_missing_landmark"]
		result["missing_landmark"] = True
	elif gms_results is not None:
		landmark_norm = norm_text(landmark)
		hits = 0
		for r in gms_results:
			if isinstance(r, dict):
				name = norm_text(r.get("name") or "")
				cat = norm_text(r.get("category") or "")
				if landmark_norm in name or name in landmark_norm or landmark_norm in cat:
					hits += 1
		result["gms_landmark"] = {
			"hits": hits,
			"total_results": gms_count,
			"matched": hits > 0,
		}
		if hits > 0:
			score += w.get("landmark_gms_hit_bonus", 0)
		else:
			score += w.get("landmark_gms_miss", 3)

	score = max(0, min(score, 80))
	ors_available = ors_result is not None and ors_result.get("found")
	gms_available = gms_results is not None
	status = "Complete" if (ors_available and gms_available) else "Partial"
	return {"score": score, "status": status, "details": result}


def _get_weights(settings_doc=None):
	from shop.integrations.signal_weights import get_weights as _gw
	return _gw(settings_doc)


def _home_country_codes(settings_doc=None):
	return home_country_codes(settings_doc)


def _province_for_city(city, settings_doc=None):
	return province_for_city(city, settings_doc)


def _canonical_cities(settings_doc=None):
	return canonical_cities(settings_doc)


def _previous_address_failed(address):
	return previous_address_failed(address)


def city_rto_rate(city: str) -> float:
	if not city:
		return 0
	# One key per place: the stats table is written with the same normalisation
	# (update_city_stats), so "Rahimyar Yar Khan" and "Rahim Yar Khan" can no
	# longer be two rows where a lookup finds neither.
	row = frappe.db.get_value(
		"Shop City Stats", {"city": normalize_city(city)}, ["orders_30d", "failed_30d", "rto_rate"], as_dict=True
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


def _address_text_score(address: dict, w: dict, settings_doc) -> tuple[int, dict]:
	"""Address quality read from the customer's own text.

	Cheap (no HTTP, one indexed count) and therefore available on both passes:
	the background evaluation used to skip these entirely and score the same
	order lower than the provisional pass had, purely because verification had
	not finished yet.
	"""
	facts: dict = {}
	score = 0
	a1 = (address.get("address_line1") or "").strip()
	city = (address.get("city") or "").strip()
	stated_province = (address.get("state") or "").strip()
	stated_country = (address.get("country") or "").strip()
	pincode = (address.get("pincode") or "").strip()
	landmark = (address.get("landmark") or "").strip()

	if stated_country and stated_country.lower() not in home_country_codes(settings_doc):
		facts["address_country_mismatch"] = stated_country
		score += w["user_country_mismatch"]
	if stated_province:
		expected = province_for_city(city, settings_doc)
		if expected and stated_province.lower() != expected.lower():
			facts["address_province_mismatch"] = stated_province
			score += w["province_mismatch"]
	if len(a1) < 5:
		score += w["address_short_line1"]
	elif not re.search(r"\d", a1):
		score += w["address_no_house_number"]
	if pincode and not re.fullmatch(r"\d{5}", pincode):
		score += w["address_bad_pincode"]
	if city and city.lower() not in canonical_cities():
		score += w["address_unknown_city"]
	if not landmark:
		facts["landmark_missing"] = True
		score += w["address_missing_landmark"]

	failures = address_failure_count(address)
	if failures:
		facts["address_prior_failures"] = failures
		score += min(failures * w["address_prior_failure_per"], w["address_prior_failure_cap"])

	# Address pressure: several different customers ordering one address in a
	# day is the drop-point pattern, and it is the one signal that survives a
	# shopper rotating phone numbers, because the address is not free to change.
	activity = address_activity(address)
	if activity["orders_24h"] >= ADDRESS_VELOCITY_CUSTOMERS and activity["customers_24h"] >= 2:
		facts["address_activity_24h"] = activity
		score += w["address_velocity"]
	return score, facts


def _score_order(inputs: dict, w: dict, settings_doc, as_of=None, exclude_order: str = "") -> tuple[dict, int]:
	"""The one scoring model. Both passes call it.

	`inputs` carries only what this caller could actually resolve: the cheap
	DB facts are resolved by whichever pass runs, the verified facts (fingerprint
	identification, IP reputation, geocoded address) appear only when the
	background pass has them. Anything absent is simply not scored - and is
	never read as "clean", which is what identity_unverified exists to say out
	loud.
	"""
	from shop.integrations.signal_weights import get_weights as _weights

	settings_doc = settings_doc or settings()
	w = w or _weights(settings_doc)
	signals: dict = {}
	score = 0
	address = inputs.get("address") or {}
	phone = inputs.get("phone") or ""
	email = (inputs.get("email") or "").strip().lower()
	city = (address.get("city") or "").strip()
	payment_method = inputs.get("payment_method") or "cod"
	fingerprint = inputs.get("device_fingerprint") or ""
	collecting = payment_method in ("cod", "pickup")

	# --- 1. how much of this identity the server can stand behind ----------
	identity = inputs.get("identity") or {}
	if identity.get("unverified"):
		signals["identity_unverified"] = True
		score += w["identity_unverified"]
	if identity.get("known_phone"):
		signals["identity_known_phone"] = True
	if identity.get("known_device"):
		signals["identity_known_device"] = True

	# --- 2. repeat history (always available) -----------------------------
	stats = order_stats(phone, email)
	signals["repeat_history"] = stats
	failed_rto = stats["failed"] + stats["rto"]
	if failed_rto:
		score += min(failed_rto * w["history_failed_rto_per"], w["history_failed_rto_cap"])
	if stats["total"] and flt(stats["cancelled"]) / stats["total"] > 0.5:
		score += w["history_cancelled_ratio_pts"]
		signals["history_cancelled"] = True

	# --- 3. blacklist ------------------------------------------------------
	if inputs.get("blacklisted"):
		signals["blacklisted"] = inputs["blacklisted"]
		score += w["blacklist_hit"]

	# --- 4. address: text now, verification when it exists ------------------
	address_delta, address_facts = _address_text_score(address, w, settings_doc)
	score += address_delta
	signals.update(address_facts)
	addr = inputs.get("addr_risk")
	if addr:
		# The verification model can reach 80 on its own and every point of it
		# comes from text the customer typed, so it contributes a capped share
		# rather than owning the score.
		contribution = min(cint(addr.get("score") or 0), ADDRESS_SCORE_CAP)
		signals["address_score"] = cint(addr.get("score") or 0)
		signals["address_score_capped_to"] = ADDRESS_SCORE_CAP
		score += contribution
		for key in (
			"geo_not_found", "city_mismatch", "wrong_country", "geo_unavailable",
			"verification_unavailable", "geo_city_mismatch", "user_country_mismatch",
			"province_mismatch",
		):
			if addr.get(key):
				signals[f"address_{key}"] = addr[key] if not isinstance(addr[key], bool) else True
		if (addr.get("gms_landmark") or {}).get("matched"):
			signals["landmark_gms"] = addr["gms_landmark"]
	elif inputs.get("addr_risk") is None and inputs.get("verification_pending"):
		signals["address_verification_pending"] = True

	# --- 5. velocity, decaying over a day --------------------------------
	profile = velocity_profile(
		phone, fingerprint, address, as_of=as_of, exclude_order=exclude_order
	)
	signals["orders_last_24h"] = profile["orders_24h"]
	signals["orders_last_60m"] = profile["last_hour"]
	signals["velocity_decayed_24h"] = profile["decayed"]
	max_per_day = cint(settings_doc.fraud_velocity_max)
	block_at = max_per_day * VELOCITY_BLOCK_MULTIPLIER
	if max_per_day and profile["orders_24h"] >= block_at:
		signals["velocity_block"] = True
		score += w["velocity_block"]
	elif profile["decayed"] > 1:
		score += min((profile["decayed"] - 1) * w["velocity_extra_per_order"], w["velocity_extra_cap"])
	if fingerprint and profile["orders_24h"] > 1 and not inputs.get("identity", {}).get("known_device"):
		signals["fp_multiple_phones"] = True
		score += w["fp_multiple_phones"]

	# --- 6. city RTO rate -------------------------------------------------
	rate = city_rto_rate(city)
	signals["city_rto_rate"] = rate
	if rate >= (cint(settings_doc.fraud_rto_high_pct) or 40):
		score += w["city_rto_high"]
	elif rate >= (cint(settings_doc.fraud_rto_medium_pct) or 20):
		score += w["city_rto_medium"]

	# --- 7. time of day ---------------------------------------------------
	if collecting and in_risky_window(settings_doc):
		signals["risky_hour"] = True
		score += w["risky_hour"]

	# --- 8. device fingerprint, when the server could verify it -----------
	if collecting and not fingerprint:
		signals["missing_fingerprint"] = True
		score += w["missing_fingerprint"]
	ident = inputs.get("fp_identification")
	if ident:
		score += _fingerprint_signals(ident, w, signals)
	elif inputs.get("fp_verify_failed"):
		# A request id that came back unverifiable is not a neutral event.
		signals["fp_verify_failed"] = True
		score += w["fp_verify_failed"]

	# --- 9. IP reputation, with "unavailable" kept distinct from "clean" ---
	ip_intel = inputs.get("ip_intel")
	if ip_intel is None:
		if inputs.get("ip_intel_enabled") and inputs.get("ip_address"):
			signals["ip_intel_unavailable"] = True
	else:
		signals["ip_intel"] = {
			"ip": inputs.get("ip_address"),
			"available": True,
			"proxy": bool(ip_intel.get("proxy")),
			"hosting": bool(ip_intel.get("hosting")),
			"abuse_score": ip_intel.get("abuse_score", 0),
			"total_reports": ip_intel.get("total_reports", 0),
			"is_tor": bool(ip_intel.get("is_tor")),
			"is_whitelisted": bool(ip_intel.get("is_whitelisted")),
			"usage_type": ip_intel.get("usage_type", ""),
		}
		if ip_intel.get("proxy"):
			score += w["ip_proxy_detected"]
		if ip_intel.get("hosting"):
			score += w["ip_hosting_detected"]
		abuse = cint(ip_intel.get("abuse_score"))
		if abuse >= 50:
			score += w["ip_abuse_high"]
		elif abuse >= 20:
			score += w["ip_abuse_medium"]
		if ip_intel.get("is_tor"):
			score += w["ip_tor_exit"]
		if cint(ip_intel.get("total_reports")) > 100:
			score += w["ip_blacklisted"]

	return signals, max(0, min(score, 100))


def _fingerprint_signals(ident: dict, w: dict, signals: dict) -> int:
	"""Verified device signals from the FingerprintJS identification payload."""
	score = 0
	bot = _fp_signal(ident, "bot")
	tampered = bool(_fp_signal(ident, "tampering") or _fp_signal(ident, "browserTampering"))
	replayed = bool(_fp_signal(ident, "replayed"))
	suspect = _normalized_score(
		_fp_signal(ident, "suspect_score") or _fp_signal(ident, "suspectScore")
	)
	blocklist = _fp_signal(ident, "ip_blocklist") or {}
	ipinfo = (_fp_signal(ident, "ip_info") or {}).get("v4") or {}
	geo = ipinfo.get("geolocation") or {}
	signals["fp_suspect_score"] = suspect
	signals["fp_bot"] = bot
	signals["fp_tampered"] = tampered
	signals["fp_replayed"] = replayed
	signals["fp_visitor_id"] = (ident.get("identification") or {}).get("visitor_id")
	signals["fp_proxy"] = bool(_fp_signal(ident, "proxy"))
	signals["fp_vpn"] = bool(_fp_signal(ident, "vpn"))
	signals["fp_virtual_machine"] = bool(_fp_signal(ident, "virtual_machine"))
	signals["fp_incognito"] = bool(_fp_signal(ident, "incognito"))
	signals["fp_network"] = {
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
	if _fp_signal(ident, "proxy"):
		score += w["proxy_detected"]
	if _fp_signal(ident, "incognito") or _fp_signal(ident, "privacy_settings"):
		score += w["incognito_privacy"]

	# Advanced device signals
	if _fp_signal(ident, "high_activity_device"):
		signals["fp_high_activity_device"] = True
		score += w["fp_high_activity_device"]
	if _fp_signal(ident, "rare_device"):
		# A first-time customer is a rare device by definition; recorded for the
		# merchant, weighted 0 unless they turn it on.
		signals["fp_rare_device"] = True
		score += w["fp_rare_device"]
	if ipinfo.get("datacenter_result"):
		signals["fp_datacenter"] = True
		score += w["fp_datacenter_ip"]
	if _fp_signal(ident, "vpn"):
		score += w["fp_vpn"]
	if _fp_signal(ident, "virtual_machine"):
		score += w["fp_virtual_machine"]
	velocity = _fp_signal(ident, "velocity") or {}
	events = velocity.get("events") or {}
	distinct_ip = velocity.get("distinct_ip") or {}
	distinct_country = velocity.get("distinct_country") or {}
	events_5m = cint(events.get("5_minutes"))
	events_1h = cint(events.get("1_hour"))
	dc_24h = cint(distinct_country.get("24_hours"))
	signals["fp_velocity"] = {
		"events_5m": events_5m,
		"events_1h": events_1h,
		"distinct_ip_1h": cint(distinct_ip.get("1_hour")),
		"distinct_country_24h": dc_24h,
	}
	if events_1h > 10:
		score += w["fp_velocity_high"]
	if events_5m > 5:
		score += w["fp_velocity_rapid_fire"]
	if cint(distinct_ip.get("1_hour")) > 1:
		score += w["fp_velocity_multi_ip"]
	if dc_24h > 1:
		score += w["fp_velocity_multi_country"]
	return score


# Signals that came from something the server owns: a lookup it performed, a
# fact it recorded, or an external service it asked. These can justify asking a
# real person for money. Everything else - a short street line, a missing
# landmark, an unknown city, a 23:00 order, no fingerprint, and the mere fact
# that we recognise nobody - is a judgement about text the customer typed, and
# that is not enough to demand a deposit.
_SERVER_EVIDENCE_FLAGS = (
	"blacklisted",
	"velocity_block",
	"address_activity_24h",
	"address_prior_failures",
	"fp_bot",
	"fp_tampered",
	"fp_replayed",
	"fp_verify_failed",
	"fp_high_activity_device",
	"fp_vpn",
	"fp_virtual_machine",
	"fp_datacenter",
	"fp_velocity_multi_country",
	"fp_velocity_rapid_fire",
	"address_geo_not_found",
	"address_geo_city_mismatch",
	"address_geo_wrong_country",
	"address_geo_unavailable",
	"address_verification_unavailable",
)


def _signal_is_set(value) -> bool:
	"""True when a signal value actually asserts something.

	Counters and nested dicts are common here: an address-activity blob of
	{"orders_24h": 0} is present but says nothing, and a failure count of zero
	is not a history. Treating "the key exists" as evidence would let an empty
	report justify a deposit.
	"""
	if value is True:
		return True
	if value is False or value is None:
		return False
	if isinstance(value, dict):
		return any(_signal_is_set(item) for item in value.values())
	if isinstance(value, (list, tuple, set)):
		return any(_signal_is_set(item) for item in value)
	if isinstance(value, (int, float)):
		return value != 0
	return bool(value)


def _has_server_evidence(signals: dict) -> bool:
	"""Did the server find something, or is this all the customer's typing?"""
	for flag in _SERVER_EVIDENCE_FLAGS:
		if _signal_is_set(signals.get(flag)):
			return True

	history = signals.get("repeat_history") or {}
	if isinstance(history, dict) and (
		_signal_is_set(history.get("failed")) or _signal_is_set(history.get("rto"))
	):
		return True
	if _signal_is_set(signals.get("history_cancelled")):
		return True

	# The device identification came back, so something is known about the
	# hardware rather than guessed from the order.
	identification = signals.get("fp_visitor_id")
	if identification:
		return True
	if flt(signals.get("fp_suspect_score")) > 0:
		return True

	# IP reputation: only the flags count, not merely having looked.
	intel = signals.get("ip_intel") or {}
	if isinstance(intel, dict):
		if any(intel.get(key) for key in ("proxy", "hosting", "is_tor", "total_reports")):
			return True
		if cint(intel.get("abuse_score")) > 0:
			return True

	# The address itself was verified and something came back that is not just
	# a clean bill of health.
	risk = signals.get("address_score")
	if risk and flt(risk) > 0:
		return True
	return False


def _verdict(
	score: int,
	signals: dict,
	hit: dict | None,
	settings_doc,
	payment_method: str,
	verified_evidence: bool = False,
) -> str:
	"""The ladder, in one place so both passes agree on it.

	Asking the customer for money is a decision about a real person, and most of
	the score is built from what that person typed: a short street line, no
	landmark, a city that is not on the list, an order at 23:00. Measured, a
	first-time shopper with a sloppy address and a privacy-respecting browser
	crosses the advance threshold on those alone - and the store loses a real
	order, and the customer's trust, over punctuation.

	So the two money bands need something the server looked up, and the review
	band does not:

	- Block: blacklist or velocity, or a very high score with verified evidence.
	- Advance Required: a score past the line *and* server-side evidence.
	- Flag: any score past the review line, on its own. Costs nothing, so it can
	  be generous.
	"""
	collecting = payment_method in ("cod", "pickup")
	advance_at = cint(settings_doc.fraud_advance_threshold) or 70
	# Review Flag Score: the line above which a human is asked to look, and
	# below which nothing happens. Only an unset field falls back - a merchant
	# who deliberately sets 0 wants every order reviewed, and `or 40` would
	# have quietly overruled them.
	flag_setting = settings_doc.get("fraud_flag_threshold")
	flag_at = 40 if flag_setting in (None, "") else cint(flag_setting)
	if hit and (collecting or cint(settings_doc.fraud_blacklist_blocks_all)):
		return "Block"
	if collecting and signals.get("velocity_block"):
		return "Block"
	if collecting and verified_evidence and score >= BLOCK_SCORE_THRESHOLD:
		signals["block_on_score_with_evidence"] = score
		return "Block"
	if collecting and score >= advance_at and _has_server_evidence(signals):
		return "Advance Required"
	if collecting and score >= advance_at:
		# Past the line, but only on what the customer typed: a human looks
		# instead of a deposit being demanded.
		signals["advance_withheld_no_server_evidence"] = score
	if score >= flag_at:
		# Flag is a queue, not a decoration: the order is written to the fraud
		# event log and marked here so the admin list can triage it before the
		# parcel moves.
		signals["requires_manual_review"] = True
		return "Flag"
	return "Pass"


def fast_risk(
	customer: dict,
	address: dict,
	payment_method: str = "cod",
	device_fingerprint: str = "",
	as_of=None,
	exclude_order=None,
) -> FraudResult:
	"""Placement-time scoring: the shared model over the cheap, DB-only facts.

	This pass cannot verify anything about the shopper, so it does not pretend
	to: the model records identity_unverified when the claimed phone and device
	match nothing the server knows, and only the two conditions that can
	refuse an order (blacklist, velocity) can produce a Block here.
	"""
	settings_doc = settings()
	phone = (customer.get("phone") or "").strip()
	email = (customer.get("email") or "").strip().lower()
	hit = blacklist_hit(phone, email)
	identity = identity_trust(phone, device_fingerprint)
	inputs = {
		"phone": phone,
		"email": email,
		"address": address,
		"payment_method": payment_method,
		"device_fingerprint": device_fingerprint,
		"blacklisted": hit.name if hit else None,
		"identity": identity,
		"verification_pending": True,
	}
	signals, score = _score_order(
		inputs, None, settings_doc, as_of=as_of, exclude_order=exclude_order or ""
	)
	verdict = _verdict(
		score,
		signals,
		hit,
		settings_doc,
		payment_method,
		verified_evidence=bool(identity.get("known_device")),
	)
	# hit_count is deliberately not touched here: the background evaluation
	# counts a hit once, and counting at placement as well inflated the same
	# order's evidence up to three times.
	return FraudResult(score, verdict, signals, False, None)


def background_fraud_task(
	order_name: str,
	customer: dict,
	address: dict,
	payment_method: str,
	device_fingerprint: str,
	fp_request_id: str,
	ip_address: str = "",
):
	"""Background job: register the order's delivery address for verification
	(status Queued - processed later by the bulk queue), then run a provisional
	fraud evaluation. The queue re-runs the evaluation once verification lands."""
	import json as _json
	from shop.integrations.verification import (
		get_or_create_verification,
		link_verification_to_order,
	)
	from shop.integrations.geocoding import address_hash as _addr_hash

	frappe.db.set_value("Sales Order", order_name, {
		"custom_ai_maps_status": "Queued",
		"custom_payment_method": payment_method or "cod",
		"custom_fraud_state": "Processing",
	})
	frappe.db.commit()

	# --- Step 1: get or create the single verification record ---
	ver = None
	try:
		ver = get_or_create_verification(address, source="Order Placement")
		frappe.db.set_value(
			"Shop Address Verification", ver["name"], {"status": "Queued"})
		frappe.db.commit()
	except Exception:
		frappe.log_error(title=f"Verification create failed for {order_name}")

	# --- Step 2: store hash + link order (queue fills in results later) ---
	try:
		frappe.db.set_value("Sales Order", order_name, {
			"custom_address_hash": _addr_hash(address),
		})
		frappe.db.commit()
	except Exception:
		frappe.log_error(title=f"Failed to store hash for {order_name}")

	if ver:
		try:
			link_verification_to_order(ver["name"], order_name,
				phone=customer.get("phone") or "", fingerprint=device_fingerprint or "")
			frappe.db.commit()
		except Exception:
			frappe.log_error(title=f"Failed to link order for {order_name}")


	# --- Step 6: Provisional fraud evaluation (no verification signals yet) ---
	try:
		# Look up IP if not passed (for older orders)
		if not ip_address:
			ip_address = frappe.db.get_value("Sales Order", order_name, "custom_client_ip") or ""
		result = evaluate_risk(customer, address, payment_method, device_fingerprint, fp_request_id,
			exclude_order=order_name, ip_address=ip_address)
		stamp_order(order_name, device_fingerprint, fp_request_id, result)
		log_fraud_event(order_name, customer, address, payment_method, device_fingerprint, result)
		frappe.db.commit()
	except Exception:
		frappe.log_error(title=f"Fraud evaluation failed for {order_name}")


def reevaluate_order_for_verification(ver_name: str) -> None:
	"""Called by the verification queue after ORS/GMS land for a record:
	re-runs the full fraud evaluation for every linked order so the score and
	verdict now include address-verification signals, then marks them Done."""
	rows = frappe.db.sql(
		"""SELECT v.name, v.address_line1, v.city, v.landmark, v.country,
			v.pincode, v.linked_orders
		FROM `tabShop Address Verification` v
		WHERE v.name = %s AND v.status NOT IN ('Queued', 'Pending')""",
		(ver_name,),
		as_dict=True,
	)
	if not rows:
		return
	row = rows[0]
	names = [s.strip() for s in (row.linked_orders or "").split(",") if s.strip()]
	if not names:
		return

	address = {
		"address_line1": row.address_line1 or "",
		"city": row.city or "",
		"landmark": row.landmark or "",
		"country": row.country or "",
		"pincode": row.pincode or "",
	}
	# Bounded: one address can carry hundreds of orders (an office, a mall),
	# and each re-evaluation costs external calls. The rest are picked up by a
	# later queue pass rather than all at once.
	batch = names[:MAX_REEVALUATE_PER_RUN]
	if len(names) > len(batch):
		frappe.logger("fraud").info(
			"fraud re-evaluation for %s capped at %s of %s linked orders",
			ver_name, len(batch), len(names),
		)
	ip_cache: dict[str, dict] = {}
	for order_name in batch:
		try:
			so = frappe.db.get_value(
				"Sales Order", order_name,
				["contact_phone", "contact_email", "custom_device_fingerprint",
				 "custom_fp_request_id", "custom_payment_method", "custom_fp_event"],
				as_dict=True,
			)
			if not so:
				continue
			reuse = None
			if so.custom_fp_event:
				# The stored event is the server's own verification result, so a
				# re-evaluation can reuse it instead of asking the API again.
				try:
					reuse = frappe.parse_json(so.custom_fp_event)
				except Exception:
					reuse = None
			customer = {
				"phone": so.contact_phone or "",
				"email": so.contact_email or "",
			}
			fingerprint = so.custom_device_fingerprint or ""
			fp_request_id = so.custom_fp_request_id or ""
			payment_method = so.custom_payment_method or "cod"
			ip_address = frappe.db.get_value("Sales Order", order_name, "custom_client_ip") or ""
			result = evaluate_risk(customer, address, payment_method,
				fingerprint, fp_request_id, exclude_order=order_name,
				ip_address=ip_address, reuse_event=reuse)
			stamp_order(order_name, fingerprint, fp_request_id, result)
			log_fraud_event(order_name, customer, address, payment_method,
				fingerprint, result)
			frappe.db.set_value("Sales Order", order_name,
				{"custom_fraud_state": "Done"})
			frappe.db.commit()
			# NOTE: AI deep analysis is intentionally MANUAL (AI usage limits).
			# Run it from Fraud Detail / order panel when needed; it needs the
			# ORS/GMS data this queue step has just persisted.
		except Exception:
			frappe.log_error(title=f"Fraud re-evaluation failed for {order_name}")


def evaluate_risk(
	customer: dict,
	address: dict,
	payment_method: str = "cod",
	device_fingerprint: str = "",
	fp_request_id: str = "",
	as_of=None,
	exclude_order: str = "",
	ip_address: str = "",
	reuse_event: dict | None = None,
) -> FraudResult:
	"""Full evaluation: the same model, with the verified facts resolved.

	`reuse_event` lets a re-evaluation work from the verification already
	snapshotted on the order instead of calling the fingerprint API again for
	an event whose answer has not changed.
	"""
	import json as _json

	settings_doc = settings()
	phone = (customer.get("phone") or "").strip()
	email = (customer.get("email") or "").strip().lower()

	# --- verified device identity ---
	raw_event = None
	fp_verified = False
	ident = None
	fp_verify_failed = False
	secret = settings_doc.get_password("fingerprint_secret_key", raise_exception=False)
	if reuse_event:
		ident = reuse_event
		raw_event = reuse_event
		fp_verified = True
	elif fp_request_id and secret:
		ident = verify_fingerprint(fp_request_id, secret, settings_doc)
		fp_verified = bool(ident)
		raw_event = ident
	elif fp_request_id:
		fp_verify_failed = True

	# --- IP reputation: unavailable is now its own answer ---
	ip_intel = None
	ip_enabled = bool(cint(settings_doc.get("ip_intel_enabled", 1)))
	if ip_address and ip_enabled:
		try:
			from shop.integrations.ip_intel import check_ip as _check_ip

			ip_intel = _check_ip(ip_address) or None
		except Exception:
			ip_intel = None

	# --- address verification, when the record has it ---
	from shop.integrations.geocoding import address_hash as _addr_hash

	ver = frappe.db.get_value(
		"Shop Address Verification",
		{"address_hash": _addr_hash(address)},
		["address_risk_status", "address_risk_score", "address_risk_json"],
		as_dict=True,
	)
	addr = None
	if ver and ver.address_risk_status in ("Complete", "Partial") and ver.address_risk_json is not None:
		try:
			addr = _json.loads(ver.address_risk_json)
			addr["score"] = ver.address_risk_score or 0
		except Exception:
			addr = None
	if addr is None and ver:
		# The record exists but has not produced a risk score yet.
		addr = {"score": 0, "verification_unavailable": True}

	ip_flagged = bool(
		ip_intel
		and (ip_intel.get("proxy") or ip_intel.get("hosting") or ip_intel.get("is_tor") or cint(ip_intel.get("abuse_score")) >= 20)
	)
	hit = blacklist_hit(phone, email)
	inputs = {
		"phone": phone,
		"email": email,
		"address": address,
		"payment_method": payment_method,
		"device_fingerprint": device_fingerprint,
		"blacklisted": hit.name if hit else None,
		"identity": identity_trust(phone, device_fingerprint, fp_verified=fp_verified, ip_flagged=ip_flagged),
		"fp_identification": ident,
		"fp_verify_failed": fp_verify_failed,
		"ip_intel": ip_intel,
		"ip_intel_enabled": ip_enabled,
		"ip_address": ip_address,
		"addr_risk": addr,
	}
	signals, score = _score_order(inputs, None, settings_doc, as_of=as_of, exclude_order=exclude_order)
	verdict = _verdict(
		score,
		signals,
		hit,
		settings_doc,
		payment_method,
		verified_evidence=bool(fp_verified or ip_flagged),
	)
	if hit:
		record_blacklist_hit(hit.name)
	return FraudResult(score, verdict, signals, fp_verified, raw_event)


def calibration_report(days: int = 90, buckets: int = 5) -> dict:
	"""How the score has actually behaved, measured from what the store recorded.

	Every order already stores its score, its verdict and (once delivery
	happened) its outcome, so the confusion matrix of the current model is one
	query - no new data, no retraining, just the numbers needed before anyone
	changes a weight. Buckets are score bands; `false_positive_rate` is the
	share of Flag/Advance/Block orders that delivered successfully (the cost of
	scaring honest customers), and `detection_rate` the share of failed or
	returned orders that the model had already marked.
	"""
	since = now_datetime() - timedelta(days=max(1, min(cint(days) or 90, 365)))
	rows = frappe.db.sql(
		"""
		SELECT COALESCE(custom_fraud_score, 0) AS score,
			custom_fraud_verdict AS verdict,
			custom_delivery_outcome AS outcome
		FROM `tabSales Order`
		WHERE docstatus = 1 AND custom_fraud_verdict IS NOT NULL AND custom_fraud_verdict != ''
			AND creation >= %s
		""",
		(since,),
		as_dict=True,
	)
	buckets = max(2, min(cint(buckets) or 5, 10))
	span = 100 / buckets
	aggregated = [
		{
			"bucket": f"{int(index * span)}-{int((index + 1) * span)}",
			"orders": 0,
			"verdicts": {"Pass": 0, "Flag": 0, "Advance Required": 0, "Block": 0},
			"delivered": 0,
			"failed_or_rto": 0,
			"pending": 0,
			"scored_high": 0,
			"bad_high": 0,
		}
		for index in range(buckets)
	]
	for row in rows:
		slot = min(buckets - 1, int(flt(row.score) / span))
		bucket = aggregated[slot]
		bucket["orders"] += 1
		if row.verdict in bucket["verdicts"]:
			bucket["verdicts"][row.verdict] += 1
		high = row.verdict != "Pass"
		if (row.outcome or "") in FAILED_OUTCOMES:
			bucket["failed_or_rto"] += 1
			if high:
				bucket["bad_high"] += 1
		elif row.outcome == "Delivered":
			bucket["delivered"] += 1
			if high:
				bucket["scored_high"] += 1
		else:
			bucket["pending"] += 1
	for bucket in aggregated:
		settled = bucket["delivered"] + bucket["failed_or_rto"]
		bucket["false_positive_rate"] = (
			round(bucket["scored_high"] / bucket["delivered"] * 100, 1) if bucket["delivered"] else None
		)
		bucket["detection_rate"] = (
			round(bucket["bad_high"] / bucket["failed_or_rto"] * 100, 1) if bucket["failed_or_rto"] else None
		)
		bucket["settled"] = settled
	return {
		"days": cint(days) or 90,
		"orders_scored": len(rows),
		"buckets": aggregated,
		"note": _(
			"Measured from the scores the store already stored. A bucket with many "
			"orders, a high false_positive_rate and no failures is a band that costs "
			"good customers more than it catches."
		),
	}


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


def stamp_order(order: str, fingerprint: str, fp_request_id: str, result: FraudResult, fingerprint_provider: str = ""):
	values = {
		"custom_device_fingerprint": fingerprint or None,
		"custom_fp_request_id": fp_request_id or None,
		"custom_fraud_score": result.score,
		"custom_fraud_verdict": result.verdict,
	}
	# Only set fingerprint_provider if explicitly provided (preserve existing value from checkout)
	if fingerprint_provider:
		values["custom_fingerprint_provider"] = fingerprint_provider
	# Include provider in signals JSON for the signal matrix
	signals = dict(result.signals) if result.signals else {}
	if fingerprint_provider:
		signals["fingerprint_provider"] = fingerprint_provider
	else:
		# Read existing provider from order for the signals JSON
		existing = frappe.db.get_value("Sales Order", order, "custom_fingerprint_provider")
		if existing:
			signals["fingerprint_provider"] = existing
	values["custom_fraud_signals"] = json.dumps(signals)
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
		WHERE so.docstatus = 1 AND LOWER(TRIM(a.city)) = %s AND so.creation >= %s
		""",
		(normalize_city(city), since),
	)[0][0]
	failed = frappe.db.sql(
		"""
		SELECT COUNT(*) FROM `tabSales Order` so
		JOIN `tabAddress` a ON a.name = so.shipping_address_name
		WHERE so.docstatus = 1 AND LOWER(TRIM(a.city)) = %s AND so.creation >= %s
		AND so.custom_delivery_outcome IN ('Failed', 'RTO')
		""",
		(normalize_city(city), since),
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
				"city": normalize_city(city),
				"orders_30d": orders,
				"failed_30d": failed,
				"rto_rate": rate,
			}
		).insert(ignore_permissions=True)


def _order_phone(so) -> str:
	"""The number this order shipped to, in the order's own words.

	Used for the feedback loop: after a failed delivery the number that has to
	be blocked is the one the courier dialled. The customer's current primary
	mobile may since have been corrected to a number that was never the problem,
	and blocking that one locks out an innocent third party.
	"""
	for field in ("contact_phone", "contact_mobile"):
		value = (so.get(field) or "").strip()
		if value:
			return value
	address_name = so.get("shipping_address_name")
	if address_name:
		value = (frappe.db.get_value("Address", address_name, "phone") or "").strip()
		if value:
			return value
	return ""


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
		# The number the courier actually dialled is the one to block - not the
		# contact's current primary, which may since have been corrected.
		phone = _order_phone(so) or customer_phone(so.customer)
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


def reset_delivery_outcome(order: str):
	"""Undo a recorded outcome when a delivery gets unmarked, so the order
	reads Pending again and a later re-delivery can be recorded. Failures are
	never cleared: the customer failure count and blacklist learned from them."""
	so = frappe.get_doc("Sales Order", order)
	current = so.custom_delivery_outcome or ""
	if current in ("", "Pending") or current in FAILED_OUTCOMES:
		return {"order": order, "outcome": current or "Pending"}
	so.db_set("custom_delivery_outcome", "Pending")
	city = frappe.db.get_value("Address", so.shipping_address_name, "city") or ""
	update_city_stats(city)
	frappe.db.commit()
	return {"order": order, "outcome": "Pending"}