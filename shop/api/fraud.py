import frappe
from frappe.utils import cint, flt

@frappe.whitelist()
def get_customer_fraud_profile(customer: str):
	"""Returns fingerprint matches and other fraud details for a customer."""
	orders = frappe.db.sql("""
		SELECT custom_device_fingerprint, shipping_address_name
		FROM `tabSales Order`
		WHERE customer = %s
	""", (customer,), as_dict=True)
	
	contacts = frappe.db.sql("""
		SELECT email_id
		FROM `tabContact` c
		JOIN `tabDynamic Link` dl ON dl.parent = c.name
		WHERE dl.link_doctype = 'Customer' AND dl.link_name = %s
	""", (customer,), as_dict=True)
	
	fingerprints = set()
	emails = set()
	address_names = set()
	
	for o in orders:
		if o.custom_device_fingerprint:
			fingerprints.add(o.custom_device_fingerprint)
		if o.shipping_address_name:
			address_names.add(o.shipping_address_name)
			
	for c in contacts:
		if c.email_id:
			emails.add(c.email_id.strip().lower())
			
	addresses = []
	if address_names:
		address_records = frappe.db.sql(f"""
			SELECT address_line1, address_line2, city, state, pincode, country
			FROM `tabAddress`
			WHERE name IN %s
		""", (tuple(address_names),), as_dict=True)
		for a in address_records:
			parts = [a.address_line1, a.address_line2, a.city, a.state, a.pincode, a.country]
			addresses.append(", ".join([str(p) for p in parts if p]))

	# Deduplicate addresses string list
	addresses = list(set(addresses))
			
	linked = []
	if fingerprints:
		fps = tuple(fingerprints)
		linked = frappe.db.sql(f"""
			SELECT name, customer, custom_fraud_score, custom_fraud_verdict, creation
			FROM `tabSales Order`
			WHERE custom_device_fingerprint IN %s
			AND customer != %s
			ORDER BY creation DESC
			LIMIT 20
		""", (fps, customer), as_dict=True)
		
	return {
		"fingerprints": list(fingerprints),
		"emails": list(emails),
		"addresses": addresses,
		"linked_orders": linked,
	}

FP_HIGHLIGHT_FIELDS = (
	"suspect_score", "bot", "bot_type", "tampering", "replayed",
	"incognito", "privacy_settings", "proxy", "proxy_confidence",
	"vpn", "virtual_machine", "developer_tools",
)

def _fp_highlights(order: str) -> dict | None:
	"""Key intelligence extracted from the raw Fingerprint event stored at
	order placement. Read-only — the snapshot is never modified."""
	import json

	raw = frappe.db.get_value("Sales Order", order, "custom_fp_event")
	if not raw:
		return None
	try:
		event = json.loads(raw)
	except Exception:
		return None

	from shop.integrations.fraud import _fp_signal, _normalized_score
	from frappe.utils import cint

	highlights = {}
	for field in FP_HIGHLIGHT_FIELDS:
		value = _fp_signal(event, field)
		if value is None:
			continue
		if isinstance(value, (bool, int, float, str)):
			highlights[field] = value

	suspect = highlights.get("suspect_score")
	if suspect is not None:
		try:
			highlights["suspect_score_raw"] = flt(suspect)
			highlights["suspect_score"] = round(_normalized_score(suspect), 2)
		except Exception:
			pass

	identification = event.get("identification") or {}
	highlights["visitor_id"] = identification.get("visitor_id") or ""
	highlights["confidence"] = ((identification.get("confidence") or {}).get("score"))

	ipinfo = (_fp_signal(event, "ip_info") or {}).get("v4") or {}
	geo = ipinfo.get("geolocation") or {}
	highlights["network"] = {
		"ip": ipinfo.get("address"),
		"city": geo.get("city_name"),
		"country": geo.get("country_name"),
		"isp": ipinfo.get("asn_name"),
		"datacenter": bool(ipinfo.get("datacenter_result")),
	}
	return highlights


@frappe.whitelist()
def get_order_fraud_profile(order: str):
	"""Snapshot view: score/verdict/signals frozen at order placement,
	plus fingerprint intelligence from the raw stored event.

	The placement snapshot is immutable evidence — this endpoint NEVER
	writes to the Sales Order."""
	so = frappe.db.get_value("Sales Order", order,
		["customer", "contact_email", "contact_mobile", "custom_device_fingerprint", "custom_fraud_score", "custom_fraud_verdict", "custom_fraud_signals", "shipping_address_name", "creation"],
		as_dict=True)
		
	if not so:
		return {}
		
	# Find other orders with same fingerprint
	fp_matches = []
	if so.custom_device_fingerprint:
		fp_matches = frappe.db.sql("""
			SELECT name, customer, custom_fraud_score, custom_fraud_verdict, creation
			FROM `tabSales Order`
			WHERE custom_device_fingerprint = %s
			AND name != %s
			ORDER BY creation DESC
			LIMIT 20
		""", (so.custom_device_fingerprint, order), as_dict=True)
		
	# Find other orders to the same address
	address_matches = []
	if so.shipping_address_name:
		address_matches = frappe.db.sql("""
			SELECT name, customer, custom_fraud_score, custom_fraud_verdict, creation
			FROM `tabSales Order`
			WHERE shipping_address_name = %s
			AND name != %s
			ORDER BY creation DESC
			LIMIT 20
		""", (so.shipping_address_name, order), as_dict=True)
		
	return {
		"fingerprint": so.custom_device_fingerprint,
		"score": so.custom_fraud_score,
		"verdict": so.custom_fraud_verdict,
		"signals": so.custom_fraud_signals,
		"customer": so.customer,
		"phone": so.contact_mobile,
		"email": so.contact_email,
		"creation": str(so.creation),
		"fp_highlights": _fp_highlights(order),
		"fp_matches": fp_matches,
		"address_matches": address_matches
	}


@frappe.whitelist()
def get_full_fp_event(order: str):
	"""Complete raw Fingerprint Identification event stored at placement."""
	import json

	raw = frappe.db.get_value("Sales Order", order, "custom_fp_event")
	if not raw:
		return {"event": None}
	try:
		return {"event": json.loads(raw)}
	except Exception:
		return {"event": None}


@frappe.whitelist()
def get_live_check(order: str):
	"""Current-risk view computed on open. Anchored to the order's placement
	time for velocity; everything else reflects NOW. Read-only."""
	from shop.integrations.fraud import (
		blacklist_hit,
		city_rto_rate,
		customers_for_phone,
	)

	so = frappe.db.get_value(
		"Sales Order",
		order,
		["customer", "contact_email", "contact_mobile", "shipping_address_name", "custom_device_fingerprint", "creation"],
		as_dict=True,
	)
	if not so:
		return {}

	from datetime import timedelta
	from frappe.utils import add_to_date, flt

	window_start = add_to_date(so.creation, minutes=-60)

	customers = customers_for_phone(so.contact_mobile or "")
	phone_before = 0
	if customers:
		phone_before = frappe.db.count(
			"Sales Order",
			{
				"name": ["!=", order],
				"docstatus": ["in", [0, 1, 2]],
				"creation": ["between", [window_start, so.creation]],
				"customer": ["in", customers],
			},
		)
	fp_around = 0
	if so.custom_device_fingerprint:
		fp_around = frappe.db.count(
			"Sales Order",
			{
				"name": ["!=", order],
				"creation": ["between", [window_start, so.creation]],
				"custom_device_fingerprint": so.custom_device_fingerprint,
			},
		)
	same_device_after = 0
	if so.custom_device_fingerprint:
		same_device_after = frappe.db.count(
			"Sales Order",
			{
				"name": ["!=", order],
				"creation": [">", so.creation],
				"custom_device_fingerprint": so.custom_device_fingerprint,
			},
		)

	hit = blacklist_hit(so.contact_mobile or "", so.contact_email)
	failed = 0
	if so.customer:
		failed = cint(frappe.db.get_value("Customer", so.customer, "custom_failed_deliveries"))

	city = frappe.db.get_value("Address", so.shipping_address_name, "city") if so.shipping_address_name else ""
	rate = city_rto_rate(city or "")

	return {
		"velocity_window": {
			"phone_orders_within_60m_of_placement": phone_before,
			"device_orders_within_60m_of_placement": fp_around,
			"same_device_orders_after": same_device_after,
		},
		"blacklisted_now": hit.name if hit else None,
		"customer_failed_deliveries": failed,
		"city": city or "",
		"city_rto_rate": flt(rate),
	}

@frappe.whitelist()
def recalculate_order_fraud(order: str):
	"""Manually recalculates the fraud score for a sales order."""
	import json
	from shop.integrations.fraud import evaluate_risk
	
	so = frappe.get_doc("Sales Order", order)
	if not so:
		frappe.throw("Sales Order not found")
		
	# Reconstruct customer and address dicts
	customer = {
		"email": so.contact_email,
		"phone": so.contact_mobile,
		"full_name": so.customer_name
	}
	
	address = {}
	if so.shipping_address_name:
		addr_doc = frappe.get_doc("Address", so.shipping_address_name)
		address = {
			"address_line1": addr_doc.address_line1,
			"address_line2": addr_doc.address_line2,
			"city": addr_doc.city,
			"state": addr_doc.state,
			"country": addr_doc.country,
			"pincode": addr_doc.pincode,
			"landmark": addr_doc.custom_landmark,
			"alt_phone": addr_doc.custom_alt_phone,
		}
		
	payment_method = "cod"
	
	# Evaluate
	fraud_res = evaluate_risk(
		customer, 
		address, 
		payment_method, 
		so.custom_device_fingerprint or "", 
		""
	)
	
	# Update SO
	frappe.db.set_value("Sales Order", so.name, {
		"custom_fraud_score": fraud_res.score,
		"custom_fraud_verdict": fraud_res.verdict,
		"custom_fraud_signals": json.dumps(fraud_res.signals)
	})
	
	return {"status": "success"}

@frappe.whitelist()
def get_related_orders(order: str):
	"""Finds related orders based on fingerprint, email, phone, and address."""
	so = frappe.db.get_value("Sales Order", order, 
		["customer", "contact_email", "contact_mobile", "shipping_address_name", "custom_device_fingerprint"], 
		as_dict=True)
	if not so:
		return {}

	matches = {}
	
	def add_matches(field, val, label):
		if not val: return
		rows = frappe.db.sql(f"""
			SELECT name, customer, custom_fraud_score, custom_fraud_verdict, creation
			FROM `tabSales Order`
			WHERE {field} = %s AND name != %s
			ORDER BY creation DESC LIMIT 5
		""", (val, order), as_dict=True)
		for r in rows:
			if r.name not in matches:
				matches[r.name] = r
				matches[r.name]["match_reasons"] = [label]
			else:
				matches[r.name]["match_reasons"].append(label)

	add_matches("custom_device_fingerprint", so.custom_device_fingerprint, "Device Fingerprint")
	add_matches("contact_email", so.contact_email, "Email")
	
	if so.contact_mobile:
		from shop.integrations.fraud import normalize_phone
		norm = normalize_phone(so.contact_mobile)
		if norm:
			rows = frappe.db.sql("""
				SELECT name, customer, custom_fraud_score, custom_fraud_verdict, creation
				FROM `tabSales Order`
				WHERE REPLACE(REPLACE(REPLACE(REPLACE(contact_mobile, ' ', ''), '-', ''), '+', ''), '(', '') LIKE %s
				AND name != %s
				ORDER BY creation DESC LIMIT 5
			""", (f"%{norm}", order), as_dict=True)
			for r in rows:
				if r.name not in matches:
					matches[r.name] = r
					matches[r.name]["match_reasons"] = ["Phone"]
				else:
					if "Phone" not in matches[r.name]["match_reasons"]:
						matches[r.name]["match_reasons"].append("Phone")

	add_matches("shipping_address_name", so.shipping_address_name, "Address")

	return {
		"fingerprint": so.custom_device_fingerprint,
		"related": sorted(matches.values(), key=lambda x: x.creation, reverse=True)
	}


@frappe.whitelist()
def get_overview() -> dict:
	"""Aggregated fraud intelligence for the overview page.

	Snapshot data (score/verdict/signals/raw fingerprint event) is captured at
	order placement and never changes. Everything returned here is computed
	live: verdict counts, averages, blacklist state, city RTO rates.

	Reads from Sales Order (every scored order carries a verdict, including
	"Pass") so the overview reflects ALL orders, not just flagged ones.
	"""
	from frappe.utils import add_days, nowdate

	def bucket(days: int) -> dict:
		since = add_days(nowdate(), -days)
		rows = frappe.get_all(
			"Sales Order",
			filters={"custom_fraud_verdict": ["is", "set"], "creation": [">=", since]},
			fields=["custom_fraud_verdict", "custom_fraud_score", "custom_device_fingerprint"],
		)
		out = {
			"total": len(rows),
			"pass": 0,
			"flag": 0,
			"advance": 0,
			"block": 0,
			"avg_score": 0,
			"fingerprinted": 0,
		}
		if rows:
			for r in rows:
				if r.custom_fraud_verdict == "Pass":
					out["pass"] += 1
				elif r.custom_fraud_verdict == "Flag":
					out["flag"] += 1
				elif r.custom_fraud_verdict == "Advance Required":
					out["advance"] += 1
				elif r.custom_fraud_verdict == "Block":
					out["block"] += 1
				if r.custom_device_fingerprint:
					out["fingerprinted"] += 1
			out["avg_score"] = round(sum(r.custom_fraud_score or 0 for r in rows) / len(rows), 1)
		return out

	recent_events = frappe.db.sql(
		"""
		SELECT so.name AS order_name, so.creation, so.customer,
			so.contact_mobile AS phone, a.city,
			so.custom_fraud_verdict AS verdict, so.custom_fraud_score AS score,
			(so.custom_device_fingerprint IS NOT NULL AND so.custom_device_fingerprint != '') AS fingerprinted,
			so.custom_delivery_outcome AS delivery_outcome
		FROM `tabSales Order` so
		LEFT JOIN `tabAddress` a ON a.name = so.shipping_address_name
		WHERE so.custom_fraud_verdict IS NOT NULL AND so.custom_fraud_verdict != ''
		ORDER BY so.creation DESC
		LIMIT 15
		""",
		as_dict=True,
	)

	blacklist = frappe.get_all(
		"Shop Blacklist",
		filters={"active": 1},
		fields=["name", "phone", "email", "reason", "source", "hit_count", "creation"],
		order_by="creation desc",
		limit=20,
	)

	cities = frappe.get_all(
		"Shop City Stats",
		fields=["city", "orders_30d", "failed_30d", "rto_rate"],
		filters={"orders_30d": [">", 0]},
		order_by="rto_rate desc",
		limit=8,
	)

	return {
		"kpis": {"today": bucket(1), "week": bucket(7), "month": bucket(30)},
		"recent_events": recent_events,
		"blacklist": blacklist,
		"cities": cities,
	}


@frappe.whitelist()
def get_customer_live(customer: str) -> dict:
	"""Current-risk snapshot for a customer, computed on open."""
	from shop.integrations.fraud import (
		blacklist_hit,
		city_rto_rate,
		customer_phone,
	)

	phone = customer_phone(customer)
	failed = cint(frappe.db.get_value("Customer", customer, "custom_failed_deliveries"))
	fp = frappe.db.get_value("Customer", customer, "custom_device_fingerprint") or ""

	emails = [
		r[0]
		for r in frappe.db.sql(
			"""
			SELECT ce.email_id FROM `tabContact Email` ce
			JOIN `tabDynamic Link` dl ON dl.parent = ce.parent
			WHERE dl.link_doctype = 'Customer' AND dl.link_name = %s
			""",
			(customer,),
		)
	]

	hit = None
	if phone or emails:
		hit = blacklist_hit(phone, emails[0] if emails else None)

	cities = [
		r[0]
		for r in frappe.db.sql(
			"""
			SELECT DISTINCT a.city FROM `tabAddress` a
			JOIN `tabDynamic Link` dl ON dl.parent = a.name
			WHERE dl.link_doctype = 'Customer' AND dl.link_name = %s AND a.city IS NOT NULL AND a.city != ''
			""",
			(customer,),
		)
	]
	city_rates = [{"city": c, "rto_rate": flt(city_rto_rate(c))} for c in cities[:5]]

	last_order = frappe.db.get_value(
		"Sales Order",
		{"customer": customer},
		["name", "creation", "custom_fraud_verdict"],
		as_dict=True,
		order_by="creation desc",
	)

	return {
		"phone": phone,
		"blacklisted_now": hit.name if hit else None,
		"blacklist_reason": (hit.reason if hit else None) or None,
		"failed_deliveries": failed,
		"last_seen_device": fp,
		"city_rates": city_rates,
		"last_order": last_order.name if last_order else None,
		"last_order_verdict": last_order.custom_fraud_verdict if last_order else None,
		"last_order_at": str(last_order.creation) if last_order else None,
	}
