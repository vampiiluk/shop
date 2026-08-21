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
	def __init__(self, score: int, verdict: str, signals: dict, fp_verified: bool = False):
		self.score = score
		self.verdict = verdict
		self.signals = signals
		self.fp_verified = fp_verified


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
	settings_doc = settings_doc or settings()
	custom = [c.strip().lower() for c in (settings_doc.pk_cities or "").split(",") if c.strip()]
	return custom or DEFAULT_PK_CITIES


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


def velocity_count(phone: str, fingerprint: str, window_minutes: int = 60) -> tuple[int, int]:
	"""Orders in the last window from this phone and (separately) this device."""
	now = now_datetime()
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
		return frappe.db.get_value(
			"Shop Blacklist",
			{"active": 1, "email": email.strip().lower()},
			["name", "phone", "email", "hit_count"],
			as_dict=True,
		)
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


def address_risk(address: dict) -> int:
	"""Address quality + historical failures at the same spot."""
	score = 0
	a1 = (address.get("address_line1") or "").strip()
	city = (address.get("city") or "").strip()
	pincode = (address.get("pincode") or "").strip()
	landmark = (address.get("landmark") or "").strip()
	if len(a1) < 5:
		score += 15  # house/street basically missing
	elif not re.search(r"\d", a1):
		score += 10  # no house/plot number
	if not re.fullmatch(r"\d{5}", pincode):
		score += 5
	if city and city.lower() not in canonical_cities():
		score += 10
	if not landmark:
		score += 15
	if previous_address_failed(address):
		score += 30
	return min(score, 60)


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


def _fp_signal(identification: dict, name: str):
	"""Smart Signals may be nested {'result': ..., 'confidence': ...} or plain values."""
	signal = (identification.get("signals") or {}).get(name)
	if isinstance(signal, dict):
		return signal.get("result")
	return signal


def evaluate_risk(
	customer: dict,
	address: dict,
	payment_method: str = "cod",
	device_fingerprint: str = "",
	fp_request_id: str = "",
) -> FraudResult:
	settings_doc = settings()
	phone = customer.get("phone") or ""
	email = (customer.get("email") or "").strip().lower()
	city = (address.get("city") or "").strip()
	signals: dict = {}
	score = 0
	fp_verified = False

	# ---- 7. device fingerprint (may verify server-side via Fingerprint Identification) ----
	if fp_request_id and settings_doc.fingerprint_secret_key:
		ident = verify_fingerprint(fp_request_id, settings_doc.fingerprint_secret_key, settings_doc)
		fp_verified = bool(ident)
		if ident:
			suspect = flt(_fp_signal(ident, "suspectScore"))
			bot = _fp_signal(ident, "bot")
			tampered = _fp_signal(ident, "browserTampering")
			incognito = _fp_signal(ident, "incognito")
			replayed = ident.get("replayed")
			signals["fp_suspect_score"] = suspect
			signals["fp_bot"] = bot
			signals["fp_tampered"] = tampered
			signals["fp_incognito"] = incognito
			signals["fp_replayed"] = replayed
			signals["fp_visitor_id"] = (ident.get("identification") or {}).get("visitor_id")
			if bot or tampered or replayed:
				score += 40
			elif suspect >= 0.8:
				score += 30
			elif suspect >= 0.5:
				score += 15
		else:
			# request id sent but verification failed -> tampered/replayed id
			signals["fp_verify_failed"] = True
			score += 30
	elif payment_method == "cod" and not device_fingerprint:
		score += 10
		signals["missing_fingerprint"] = True

	# ---- 1. repeat fraud history ----
	stats = order_stats(phone, email)
	signals["repeat_history"] = stats
	failed_rto = stats["failed"] + stats["rto"]
	if failed_rto:
		score += min(failed_rto * 15, 30)
	if stats["total"] and flt(stats["cancelled"]) / stats["total"] > 0.5:
		score += 10
		signals["history_cancelled"] = True

	# ---- 2. phone blacklist ----
	hit = blacklist_hit(phone, email)
	if hit:
		signals["blacklisted"] = hit.name
		score += 40

	# ---- 3. address risk ----
	addr_risk = address_risk(address)
	signals["address_score"] = addr_risk
	score += addr_risk

	# ---- 4. order velocity ----
	orders_1hr, fp_1hr = velocity_count(phone, device_fingerprint, 60)
	signals["orders_last_60m"] = orders_1hr
	signals["fp_orders_last_60m"] = fp_1hr
	max_per_hour = cint(settings_doc.fraud_velocity_max)
	if max_per_hour and orders_1hr >= max_per_hour:
		signals["velocity_block"] = True
		score += 40
	elif orders_1hr > 1:
		score += min((orders_1hr - 1) * 15, 30)
	if device_fingerprint and fp_1hr > orders_1hr:
		signals["fp_multiple_phones"] = True
		score += 25

	# ---- 5. city RTO rate ----
	rate = city_rto_rate(city)
	signals["city_rto_rate"] = rate
	if rate >= 40:
		score += 30
	elif rate >= 20:
		score += 15

	# ---- 6. time-of-day pattern ----
	if payment_method == "cod" and in_risky_window(settings_doc):
		signals["risky_hour"] = True
		score += 15

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
	return FraudResult(score, verdict, signals, fp_verified)


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
	frappe.db.set_value(
		"Sales Order",
		order,
		{
			"custom_device_fingerprint": fingerprint or None,
			"custom_fp_request_id": fp_request_id or None,
			"custom_fraud_score": result.score,
			"custom_fraud_signals": json.dumps(result.signals),
			"custom_fraud_verdict": result.verdict,
		},
	)


def add_to_blacklist(phone: str, reason: str, source: str = "Manual", email: str | None = None):
	if not normalize_phone(phone):
		return None
	existing = blacklist_hit(phone, email)
	if existing:
		return existing.name
	doc = frappe.get_doc(
		{
			"doctype": "Shop Blacklist",
			"phone": phone,
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