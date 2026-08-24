"""Shop capabilities exposed to the store assistant.

Every tool is a thin wrapper over the same admin API the panel uses, so the
assistant can only do what a Shop Manager could do by hand.
"""

from __future__ import annotations

import csv as _csv
import json as _json
import os as _os
import subprocess as _subprocess
import tempfile as _tempfile
from typing import Any

import frappe
from flow import tool
from flow.lib.model import Model as _FlowModel

from shop.api import analytics, carts, customers, discounts, inventory
from shop.api import orders as orders_api
from shop.api import products as products_api
from shop.api import reviews as reviews_api
from shop.api import settings as settings_api
from shop.api import variants as variants_api


# ---------------------------------------------------------------------------
# Google Maps Scraper helpers
# ---------------------------------------------------------------------------

def _get_gms_bin() -> str:
	"""Return GMS binary path, auto-downloading if missing."""
	from shop.integrations.gms import get_gms_binary, ensure_gms

	bin_path = get_gms_binary()
	return bin_path if bin_path else ensure_gms()


def _search_google_maps_batch_by_id(
	items: list[tuple[str, str]], depth: int = 5, concurrency: int = 0
) -> dict[str, list[dict]] | None:
	"""Run multiple GMS queries in ONE subprocess, mapping results back per query.

	items: list of (result_id, query). Uses GMS's custom input-id syntax
	('query #!#id') so every CSV row echoes its source via the input_id column,
	letting us attribute results to individual verification records even when
	-c N runs queries concurrently. Returns {result_id: [results]}, or None on
	infrastructure failure (anti-bot page / timeout) after one retry."""
	if not items:
		return {}

	result = _run_gms_batch_once(items, depth=depth, concurrency=concurrency)
	if result is None:
		# Google intermittently serves a consent/anti-bot page. A short cool
		# -down + fresh browser profile clears it in most cases.
		import time as _time

		_time.sleep(20)
		result = _run_gms_batch_once(items, depth=depth, concurrency=concurrency)
	return result


def _run_gms_batch_once(
	items: list[tuple[str, str]], depth: int = 5, concurrency: int = 0
) -> dict[str, list[dict]] | None:
	query_file = _tempfile.mktemp(suffix=".txt")
	results_file = _tempfile.mktemp(suffix=".csv")

	try:
		with open(query_file, "w") as f:
			for rid, q in items:
				f.write(f"{q} #!#{rid}\n")

		concurrency = max(1, int(concurrency or 0))
		cmd = [
			_get_gms_bin(), "-input", query_file, "-results", results_file,
			"-lang", "en", "-depth", str(depth),
		]
		if concurrency > 1:
			cmd += ["-c", str(concurrency)]

		# each query takes ~20s wall time regardless of depth; queries run
		# `concurrency`-at-a-time, so scale the timeout with batch size
		batches = max(1, -(-len(items) // concurrency))
		timeout = 90 + batches * 60

		_os.makedirs("/tmp/frappe_logs", exist_ok=True)
		proc = _subprocess.run(
			cmd,
			capture_output=True,
			timeout=timeout,
			env={**_os.environ, "FRAPPE_LOG_DIR": "/tmp/frappe_logs"},
		)
		stderr_tail = proc.stderr.decode(errors="replace")[-4000:] if proc.stderr else ""

		grouped: dict[str, list[dict]] = {}
		if _os.path.exists(results_file):
			with open(results_file, "r") as f:
				for row in _csv.reader(f):
					if len(row) > 15 and row[2] != "title":
						grouped.setdefault(row[0], []).append({
							"name": row[2],
							"address": row[4],
							"category": row[3],
							"phone": row[8],
							"lat": row[13],
							"lng": row[14],
						})

		# Zero rows + scraper errors means Google served an anti-bot/consent
		# page - that is an infrastructure failure, not a legit empty search.
		if not grouped and ("unexpected page type" in stderr_tail or proc.returncode != 0):
			return None
		return grouped

	except Exception:
		return None

	finally:
		for path in (query_file, results_file):
			try:
				_os.unlink(path)
			except Exception:
				pass


def _search_google_maps_batch(queries: list[str], depth: int = 5, max_results: int = 5) -> list[dict] | None:
	"""Run multiple GMS queries in a single subprocess (one Chromium instance).
	Returns merged, deduplicated results across all queries.
	Returns None on infrastructure failure (anti-bot page, timeout)."""
	grouped = _search_google_maps_batch_by_id(
		[(f"q{i}", q) for i, q in enumerate(queries)], depth=depth
	)
	if grouped is None:
		return None

	seen: set[str] = set()
	results: list[dict] = []
	for rows in grouped.values():
		for r in rows:
			key = f"{r['name']}|{r['address']}"
			if key not in seen:
				seen.add(key)
				results.append(r)

	return results[:max_results]


def _search_google_maps(query: str, depth: int = 5, max_results: int = 5) -> list[dict]:
	"""Search Google Maps via local GMS scraper. Returns top N closest matches."""
	query_file = _tempfile.mktemp(suffix=".txt")
	results_file = _tempfile.mktemp(suffix=".csv")

	try:
		with open(query_file, "w") as f:
			f.write(query + "\n")

		_os.makedirs("/tmp/frappe_logs", exist_ok=True)
		_subprocess.run(
			[_get_gms_bin(), "-input", query_file, "-results", results_file,
			 "-lang", "en", "-depth", str(depth)],
			capture_output=True,
			timeout=60,
			env={**_os.environ, "FRAPPE_LOG_DIR": "/tmp/frappe_logs"},
		)

		if not _os.path.exists(results_file):
			return []

		results: list[dict] = []
		with open(results_file, "r") as f:
			for row in _csv.reader(f):
				if len(row) > 15 and row[2] != "title":
					results.append({
						"name": row[2],
						"address": row[4],
						"category": row[3],
						"phone": row[8],
						"lat": row[13],
						"lng": row[14],
					})

		return results[:max_results]

	except Exception:
		return []

	finally:
		for path in (query_file, results_file):
			try:
				_os.unlink(path)
			except Exception:
				pass


def _search_address_on_maps(address: dict, landmark: str, depth: int = 5) -> list[dict]:
	"""Search Maps for the address using both street address and landmark.
	Runs both queries in a single GMS subprocess (one Chromium instance)."""
	addr_parts = [
		address.get("address_line1") or address.get("line1", ""),
		address.get("address_line2") or address.get("line2", ""),
		address.get("city", ""),
		address.get("state") or address.get("province", ""),
		address.get("country", ""),
	]
	addr_query = " ".join(p for p in addr_parts if p).strip()

	queries = []
	if addr_query:
		queries.append(addr_query)
	if landmark:
		city = address.get("city", "")
		queries.append(f"{landmark} {city}".strip())

	if not queries:
		return []

	results = _search_google_maps_batch(queries, depth=depth, max_results=5)
	return results[:5]


def _format_maps_results(results: list[dict]) -> str:
	"""Format Maps results as human-readable text for the AI prompt."""
	if not results:
		return "No Google Maps results found."

	lines: list[str] = []
	for i, r in enumerate(results, 1):
		lines.append(f"{i}. {r['name']}")
		lines.append(f"   Address: {r['address']}")
		if r.get("category"):
			lines.append(f"   Category: {r['category']}")
		if r.get("lat") and r.get("lng"):
			lines.append(f"   Coordinates: {r['lat']}, {r['lng']}")
		lines.append("")

	return "\n".join(lines)


def _get_address_pre_check(address: dict) -> list[str]:
	"""Detect obvious address issues before AI call."""
	issues: list[str] = []
	pincode = address.get("pincode", "")
	city = address.get("city", "")
	line1 = address.get("line1", "")

	if pincode and city:
		city_lower = city.lower()
		if pincode.startswith("64") and "lahore" in city_lower:
			issues.append(f"Pincode {pincode} is for Rahim Yar Khan, not Lahore")
		elif pincode.startswith("54") and "rahim" in city_lower:
			issues.append(f"Pincode {pincode} is for Lahore, not {city}")
		elif pincode.startswith("75") and "lahore" in city_lower:
			issues.append(f"Pincode {pincode} is for Karachi, not Lahore")

	if "johar town" in line1.lower() and not any(
		b in line1.lower() for b in ("block", "phase", "plot")
	):
		issues.append("Johar Town address missing block/phase designation")

	if "house no" in line1.lower() and "street" not in line1.lower() and "block" not in line1.lower():
		issues.append("House number without street or block — address may be incomplete")

	return issues


# ---------------------------------------------------------------------------
# AI Fraud Scoring helpers
# ---------------------------------------------------------------------------

_ORDER_PROMPT = """You are a senior fraud analyst for an online store in Pakistan. Perform a deep, independent fraud analysis of this order. You are NOT given any pre-computed verdict — form your own.

=== ORDER (PII-censored) ===
{order_data}

=== ADDRESS VERIFICATION: ORS GEOCODING ===
{ors_results}

=== ADDRESS VERIFICATION: GOOGLE MAPS ===
{maps_results}

=== PRE-DETECTED STATIC ISSUES ===
{pre_check_issues}

=== DEEP EVIDENCE (live aggregates) ===
{deep_evidence}

=== ANALYSIS METHOD ===
Assess EACH domain separately before scoring:
1. address_consistency — Does the stated address+landmark reconcile with ORS and Google Maps? Consider geocode confidence/match type, house number presence, distance between ORS coords and Maps places, landmark hits, business vs residential character.
2. device_trust — Fingerprint signals: bot/tampering/replay, suspect score, VPN/proxy/datacenter/VM/incognito, IP blocklist, device velocity events, IP-vs-address geography.
3. behavioral — Customer history: failed deliveries, RTO, cancellations, order count; current-order velocity from OTHER orders on same phone/device in the last 60 minutes; blacklist status.
4. geographic — City RTO rate, province/country mismatches, area character from Maps results.
5. payment — COD vs prepaid, amount anomalies vs items, missing fingerprint on COD.

RULES:
- Missing verification data must lower your confidence and be listed in address_issues — do not silently treat unknown as safe.
- Corroborating evidence across domains should reinforce each other; a single strong red flag can dominate.
- Do NOT simply restate numbers given to you; reason about what they MEAN together.
- score is your holistic 0-100 risk assessment.

Return ONLY this JSON:
{{
  "domain_scores": {{"address_consistency": <0-100>, "device_trust": <0-100>, "behavioral": <0-100>, "geographic": <0-100>, "payment": <0-100>}},
  "score": <0-100>,
  "reasoning": "<3-6 sentences citing specific evidence across at least 3 domains>",
  "confidence": "<low|medium|high>",
  "address_verified": <true|false>,
  "address_issues": ["<inconsistencies incl. missing data sources>"],
  "key_risks": ["<risk1>", "<risk2>"]
}}"""

_CUSTOMER_PROMPT = """You are a fraud analyst for an online store. Analyze this customer's fraud risk profile.

Customer data:
{customer_data}

TASK:
1. Assess whether the customer has suspicious patterns (multiple addresses, device sharing, etc.).
2. Evaluate the lifetime spend and order count for anomalies.

Return a JSON object with exactly these fields:
{{
  "score": <integer 0-100, where 0=no risk and 100=definite fraud>,
  "reasoning": "<2-4 sentences explaining the key risk factors>",
  "confidence": "<low|medium|high>",
  "key_risks": ["<risk1>", "<risk2>"]
}}

Return ONLY the JSON object, no other text."""


def _get_ai_model() -> _FlowModel:
	"""Use the same Flow Model the Shop Assistant runs on."""
	from shop.agent.setup import AGENT_TITLE, chat_model

	model_name = frappe.db.get_value("Flow Agent", AGENT_TITLE, "model")
	model_name = model_name or chat_model()
	if not model_name:
		frappe.throw(
			"No Flow Model configured for the Shop Assistant. "
			"Set up a chat model in the flow app to enable AI scoring."
		)
	return _FlowModel(model_name)


def _call_ai(prompt: str) -> str:
	"""Call the configured AI model. Maps data is pre-fetched."""
	model = _get_ai_model()
	response = model.chat(prompt)
	return response.content or ""


def _parse_ai_json(raw: str) -> dict[str, Any]:
	"""Extract JSON from AI response, handling markdown code fences."""
	text = raw.strip()
	if text.startswith("```"):
		lines = [line for line in text.split("\n") if not line.startswith("```")]
		text = "\n".join(lines)

	try:
		return _json.loads(text)
	except _json.JSONDecodeError:
		start, end = text.find("{"), text.rfind("}") + 1
		if start >= 0 and end > start:
			return _json.loads(text[start:end])
		return {"score": 50, "reasoning": text, "confidence": "low"}


def _norm01(v) -> float:
	try:
		return max(0.0, min(1.0, float(v)))
	except (TypeError, ValueError):
		return 0.0


def _collect_order_signals(order) -> dict[str, Any]:
	"""Extract fraud signals from Sales Order fields."""
	signals: dict[str, Any] = {}

	if order.custom_fraud_signals:
		try:
			signals = _json.loads(order.custom_fraud_signals)
		except (_json.JSONDecodeError, TypeError):
			pass

	if order.custom_fp_event:
		try:
			fp = _json.loads(order.custom_fp_event)
			signals["fingerprint"] = {
				"bot": fp.get("bot"),
				"proxy": fp.get("proxy"),
				"vpn": fp.get("vpn"),
				"incognito": fp.get("incognito"),
				"tampering": fp.get("tampering"),
				"replayed": bool(fp.get("replayed")),
				"virtual_machine": fp.get("virtual_machine"),
				"high_activity": fp.get("high_activity_device"),
				"rare_device": fp.get("rare_device"),
				"suspect_score": _norm01(fp.get("suspect_score") or fp.get("suspectScore")),
				"ip_blocklist": fp.get("ip_blocklist") or {},
				"ip_info": (fp.get("ip_info") or {}).get("v4") or {},
				"network": fp.get("network"),
				"velocity": fp.get("velocity"),
			}
		except (_json.JSONDecodeError, TypeError):
			pass

	return signals


def _get_order_address(order) -> dict[str, str]:
	"""Pull address from linked Address doctype."""
	address: dict[str, str] = {}
	if not order.shipping_address_name:
		return address
	try:
		addr = frappe.get_doc("Address", order.shipping_address_name)
		address = {
			"line1": addr.address_line1 or "",
			"line2": addr.address_line2 or "",
			"city": addr.city or "",
			"province": addr.state or "",
			"country": addr.country or "",
			"pincode": addr.pincode or "",
			"landmark": addr.get("custom_landmark") or "",
		}
	except Exception:
		pass
	return address


# ---------------------------------------------------------------------------
# Shop Tools
# ---------------------------------------------------------------------------

@tool
def store_overview() -> dict:
	"""Sales and store health: revenue, orders, average order value, conversion,
	top products, plus counts of unfulfilled orders, low stock items and open carts."""
	return {"performance": analytics.get_overview(days=30), "today": _dashboard()}


def _dashboard() -> dict:
	from shop.api.admin import get_dashboard
	return get_dashboard()


@tool
def list_products(search: str | None = None, status: str | None = None) -> dict:
	"""List storefront products with price, stock and publish state.
	status can be "published" or "draft"."""
	return products_api.get_products(search=search, status=status, limit=50)


@tool
def product_details(product: str) -> dict:
	"""Everything about one product, including images, pricing, highlights and variants.
	Pass the product slug, for example "ceramic-mug"."""
	return products_api.get_product(product)


@tool(requires_confirmation=True)
def add_product(
	product_name: str,
	price: float,
	short_description: str | None = None,
	description: str | None = None,
	compare_at_price: float | None = None,
	opening_stock: float = 0,
	collections: list[str] | None = None,
	published: bool = True,
) -> dict:
	"""Create a new product, including its catalogue item, price and opening stock."""
	return products_api.create_product(
		product_name=product_name,
		price=price,
		short_description=short_description,
		description=description,
		compare_at_price=compare_at_price,
		opening_stock=opening_stock,
		collections=collections,
		published=published,
	)


@tool(requires_confirmation=True)
def update_product(
	product: str,
	product_name: str | None = None,
	price: float | None = None,
	compare_at_price: float | None = None,
	short_description: str | None = None,
	description: str | None = None,
	highlights: str | None = None,
	collections: list[str] | None = None,
	published: bool | None = None,
) -> dict:
	"""Change a product. Only the fields you pass are updated. highlights is one bullet per line."""
	payload = {"name": product}
	current = products_api.get_product(product)
	for field, value in {
		"product_name": product_name,
		"price": price,
		"compare_at_price": compare_at_price,
		"short_description": short_description,
		"description": description,
		"highlights": highlights,
		"collections": collections,
		"published": published,
	}.items():
		payload[field] = current.get(field) if value is None else value
	return products_api.save_product(payload)


@tool(requires_confirmation=True)
def add_product_with_options(
	product_name: str, options: list[dict], price: float, opening_stock: float = 0
) -> dict:
	"""Create a product that varies by options and build every combination.
	options looks like [{"attribute": "Size", "values": ["Small", "Large"]}]."""
	return variants_api.create_variant_product(
		product_name=product_name, options=options, price=price, opening_stock=opening_stock
	)


@tool
def list_orders(
	status: str | None = None,
	customer: str | None = None,
	limit: int = 20,
) -> list[dict]:
	"""Recent orders. status can be "Draft", "To Deliver", "Completed", etc."""
	return orders_api.get_orders(status=status, customer=customer, limit=limit)


@tool
def order_details(order: str) -> dict:
	"""One order in full: items, totals, customer, address and activity timeline."""
	return orders_api.get_order(order)


@tool
def list_customers(search: str | None = None) -> dict:
	"""Customers with how many orders they placed and what they spent."""
	return customers.get_customers(search=search, limit=50)


@tool
def customer_details(customer: str) -> dict:
	"""One customer with their orders, addresses and reviews."""
	return customers.get_customer(customer)


@tool
def list_reviews(product: str | None = None, rating: int | None = None) -> list[dict]:
	"""Product reviews, optionally filtered by product or rating."""
	return reviews_api.get_reviews(product=product, rating=rating)


@tool(requires_confirmation=True)
def delete_review(review: str) -> str:
	"""Remove a review. Use the review id from list_reviews."""
	reviews_api.delete_review(review)
	return f"Deleted review {review}"


@tool
def list_discounts() -> list:
	"""Coupon codes with their value, usage and validity."""
	return discounts.get_coupons()


@tool(requires_confirmation=True)
def create_discount(
	coupon_code: str,
	discount_type: str,
	value: float,
	min_amt: float = 0,
	maximum_use: int = 0,
	valid_upto: str | None = None,
) -> str:
	"""Create a coupon code shoppers can enter at checkout.
	discount_type is "Percentage" or "Amount". valid_upto is YYYY-MM-DD."""
	discounts.save_coupon(
		{
			"coupon_code": coupon_code,
			"discount_type": discount_type,
			"value": value,
			"min_amt": min_amt,
			"maximum_use": maximum_use,
			"valid_upto": valid_upto,
			"enabled": True,
		}
	)
	return f"Created coupon {coupon_code.upper()}"


@tool(requires_confirmation=True)
def set_discount_enabled(coupon: str, enabled: bool) -> str:
	"""Turn a coupon on or off. Use the coupon id from list_discounts."""
	discounts.set_enabled(coupon, enabled)
	return f"{'Enabled' if enabled else 'Disabled'} {coupon}"


@tool
def store_settings() -> dict:
	"""Current store configuration: payments, shipping, catalogue defaults and storefront theme."""
	return settings_api.get_settings()


@tool(requires_confirmation=True)
def update_store_settings(
	store_name: str | None = None,
	enable_cod: bool | None = None,
	flat_shipping_rate: float | None = None,
	free_shipping_above: float | None = None,
	low_stock_threshold: int | None = None,
	allow_out_of_stock: bool | None = None,
) -> dict:
	"""Change store settings. Only the values you pass are updated."""
	payload = {
		field: value
		for field, value in {
			"store_name": store_name,
			"enable_cod": enable_cod,
			"flat_shipping_rate": flat_shipping_rate,
			"free_shipping_above": free_shipping_above,
			"low_stock_threshold": low_stock_threshold,
			"allow_out_of_stock": allow_out_of_stock,
		}.items()
		if value is not None
	}
	settings_api.save_settings(payload)
	return settings_api.get_settings()


@tool
def list_collections() -> list[dict]:
	"""Product collections (categories) with item counts."""
	return products_api.get_collections()


@tool
def inventory_report() -> dict:
	"""Stock levels across warehouses for all products."""
	return inventory.get_stock_summary()


@tool(requires_confirmation=True)
def adjust_stock(product: str, warehouse: str, qty: float, reason: str) -> str:
	"""Create a stock entry to adjust inventory. Use negative qty to reduce."""
	inventory.adjust_stock(product, warehouse, qty, reason)
	return f"Adjusted {product} by {qty} in {warehouse}"


@tool
def list_open_carts() -> list[dict]:
	"""Carts abandoned or in-progress with item count and total."""
	return carts.get_open_carts()


@tool
def order_shipment(order: str) -> dict | None:
	"""The shipment raised for an order, with its status and tracking."""
	from shop.fulfillment import service
	return service.for_order(order)


@tool(requires_confirmation=True)
def send_to_fulfillment(order: str, provider: str | None = None) -> dict:
	"""Hand an order to a fulfillment provider so they pick, pack and ship it."""
	from shop.fulfillment import service
	return service.summary(service.send(order, provider))


@tool(requires_confirmation=True)
def record_shipment(order: str, carrier: str | None = None, tracking_number: str | None = None) -> dict:
	"""Mark an order you packed yourself as shipped, with optional tracking details."""
	from shop.api.fulfillment import mark_shipped
	from shop.fulfillment import service

	existing = service.for_order(order)
	name = existing["name"] if existing else service.send(order, "manual")
	return mark_shipped(name, carrier=carrier, tracking_number=tracking_number)


@tool(requires_confirmation=True)
def fulfill_order(order: str) -> dict:
	"""Ship an order, which files the delivery and reduces stock."""
	return orders_api.fulfill(order)


@tool(requires_confirmation=True)
def mark_order_paid(order: str) -> dict:
	"""Record payment against an order."""
	return orders_api.mark_paid(order)


@tool(requires_confirmation=True)
def cancel_order(order: str) -> dict:
	"""Cancel an order."""
	return orders_api.cancel_order(order)


@tool
def list_variants(product: str) -> dict:
	"""Variants of a product with their price, stock and availability."""
	return variants_api.get_variants(product)


@tool(requires_confirmation=True)
def update_variant(
	item_code: str, price: float | None = None, stock: float | None = None, available: bool | None = None
) -> dict:
	"""Change one variant's price, stock level or whether it can be bought."""
	disabled = None if available is None else not available
	return variants_api.update_variant(item_code, price=price, stock=stock, disabled=disabled)


@tool
def stock_levels(search: str | None = None, low_only: bool = False) -> dict:
	"""Current stock for every sellable item, with low stock flagged."""
	return inventory.get_inventory(search=search, low_only=low_only, limit=100)


@tool(requires_confirmation=True)
def set_stock(item_code: str, qty: float) -> dict:
	"""Set an item's stock to an exact quantity."""
	return inventory.set_stock(item_code, qty)


@tool
def open_carts() -> dict:
	"""Carts shoppers left behind, with their contents and value."""
	return carts.get_carts(status="Active", limit=50)


@tool
def setup_progress() -> list:
	"""What is still left to do before the store is ready to sell."""
	from shop.api.admin import get_setup_guide
	return get_setup_guide()


@tool(requires_confirmation=True)
def load_sample_catalog() -> str:
	"""Fill an empty store with sample products, collections and reviews to try things out."""
	frappe.enqueue("shop.demo.setup", queue="long", job_id="shop-demo-setup")
	return "Sample catalog is being created. It appears in a few seconds."


@tool
def storefront_pages() -> list:
	"""The live storefront pages and their addresses, so they can be opened or edited in Builder."""
	settings = frappe.get_cached_doc("Shop Settings")
	return [
		{"route": f"/{row.route}", "page": row.page, "edit_in_builder": f"/builder/page/{row.page}"}
		for row in settings.theme_pages
	]


@tool
def fulfillment_providers() -> list:
	"""Who can ship orders for this store, and whether each is set up."""
	from shop.fulfillment.provider import available
	return available()


# ---------------------------------------------------------------------------
# AI Fraud Scoring
# ---------------------------------------------------------------------------


def _do_score_order_risk(order_id: str) -> dict:
	"""Core scoring logic — reads pre-computed ORS + GMS from verification cache, calls AI.
	No scraping here; ORS runs synchronously in background_fraud_task, GMS runs async."""
	from shop.integrations.pii import censor_order_for_ai
	from shop.integrations.geocoding import address_hash

	order = frappe.get_doc("Sales Order", order_id)
	address = _get_order_address(order)

	order_data = {
		"name": order.name,
		"customer_name": order.customer_name,
		"grand_total": order.grand_total,
		"currency": order.currency,
		"payment_method": order.get("custom_payment_method"),
		"payment_status": order.get("custom_payment_status"),
		"items": [
			{"item_name": item.item_name, "qty": item.qty, "rate": item.rate}
			for item in order.items
		],
		"email": order.contact_email,
		"phone": order.contact_phone,
		**address,
	}

	signals = _collect_order_signals(order)
	address_issues = _get_address_pre_check(address)

	# --- Read ORS + GMS + combined risk from the single verification cache ---
	ors_results_text = ""
	hkey = address_hash(address)
	addr_verification = frappe.db.get_value(
		"Shop Address Verification",
		{"address_hash": hkey},
		["ors_status", "ors_result_json", "gms_status", "gms_result_json", "gms_result_text",
		 "address_risk_status", "address_risk_score", "address_risk_json"],
		as_dict=True,
	)

	if addr_verification and addr_verification.ors_status == "Complete" and addr_verification.ors_result_json:
		try:
			ors_data = _json.loads(addr_verification.ors_result_json)
			ors_results_text = (
				f"ORS geocoding found: {ors_data.get('label', 'N/A')}\n"
				f"Confidence: {ors_data.get('confidence', 'N/A')}, "
				f"Match type: {ors_data.get('match_type', 'N/A')}\n"
				f"Coordinates: {ors_data.get('lat')}, {ors_data.get('lng')}\n"
				f"Local area: {ors_data.get('local_area', 'N/A')}, "
				f"Admin area: {ors_data.get('admin_area', 'N/A')}\n"
				f"Country: {ors_data.get('country', 'N/A')}, "
				f"House number: {'yes' if ors_data.get('house_number') else 'no'}"
			)
		except Exception:
			ors_results_text = "ORS geocoding data present but could not be parsed."
	elif addr_verification and addr_verification.ors_status == "Failed":
		ors_results_text = "ORS geocoding FAILED — data not available for this address."
	elif addr_verification and addr_verification.ors_status == "Pending":
		ors_results_text = "ORS geocoding is still running — data not yet available."
	else:
		ors_results_text = "ORS geocoding MISSING — no verification record found for this address."

	# Append combined address verification risk summary
	risk_details = None
	if addr_verification and addr_verification.address_risk_status in ("Complete", "Partial") and addr_verification.address_risk_json:
		try:
			risk_details = _json.loads(addr_verification.address_risk_json)
			ors_results_text += (
				f"\n\nAddress verification risk score: {addr_verification.address_risk_score}/80"
				f"\nRisk flags: {', '.join(k for k in risk_details if k not in ('score', 'geo', 'gms', 'gms_landmark') and risk_details[k])}"
			)
			if risk_details.get("gms"):
				gms = risk_details["gms"]
				ors_results_text += f"\nGMS results: {gms.get('result_count', 0)} found"
				if gms.get("coords_mismatch"):
					ors_results_text += " (coordinates mismatch with ORS)"
				if gms.get("no_business_categories"):
					ors_results_text += " (no business categories — residential area?)"
			gms_lm = risk_details.get("gms_landmark") or {}
			if gms_lm:
				if gms_lm.get("matched"):
					ors_results_text += f"\nLandmark match: {gms_lm.get('hits', 0)} GMS results match the stated landmark"
				else:
					ors_results_text += "\nLandmark match: no GMS results match the stated landmark"
		except Exception:
			pass

	# --- Read GMS from order fields (saved by maps_verification_task) ---
	maps_status = order.get("custom_ai_maps_status") or "Disabled"
	maps_results_text = order.get("custom_ai_maps_results") or ""
	maps_results: list[dict] = []

	if order.get("custom_ai_maps_json"):
		try:
			maps_results = _json.loads(order.custom_ai_maps_json)
		except Exception:
			pass

	if maps_status == "Pending":
		maps_results_text = "Google Maps verification is still running — results not yet available."
	elif maps_status == "Failed":
		maps_results_text = "Google Maps verification FAILED — data not available."
	elif maps_status == "Disabled":
		maps_results_text = "Google Maps verification is disabled in Shop Settings."
	elif not maps_results_text:
		maps_results_text = "Google Maps verification data not available."

	# Landmark match info flows through risk_details above; drop stale POI key
	signals.pop("landmark_poi_match", None)

	# --- Deep evidence: customer history, live velocity, city stats, blacklist ---
	from shop.integrations.fraud import (
		order_stats,
		velocity_count,
		city_rto_rate,
		blacklist_hit,
	)

	phone = order.contact_phone or order.contact_mobile or ""
	email = order.contact_email or ""
	history = order_stats(phone, email)
	history["failed_deliveries_on_customer"] = frappe.utils.cint(
		frappe.db.get_value("Customer", order.customer, "custom_failed_deliveries"))

	orders_60m, fp_60m = velocity_count(
		phone, order.custom_device_fingerprint or "", 60, exclude_order=order.name)

	bl = blacklist_hit(phone, email)

	city = (address.get("city") or "").strip()
	deep_evidence = {
		"verification": {
			"record_status": (addr_verification.get("address_risk_status") if addr_verification else None),
			"address_risk_score_of_80": (addr_verification.get("address_risk_score") if addr_verification else None),
			"breakdown": risk_details if isinstance(risk_details, dict) else None,
			"gms_status": maps_status,
			"gms_places": [
				{"name": r.get("name"), "category": r.get("category")}
				for r in maps_results[:5] if isinstance(r, dict)
			],
		},
		"customer_history_90d": {
			"total_orders": history.get("total", 0),
			"failed_deliveries": history.get("failed", 0),
			"rto": history.get("rto", 0),
			"cancelled": history.get("cancelled", 0),
			"failed_deliveries_flag_on_customer": history.get("failed_deliveries_on_customer", 0),
		},
		"velocity_now": {
			"other_orders_same_phone_last_60m": orders_60m,
			"other_orders_same_device_last_60m": fp_60m,
		},
		"city_risk": {"city": city or None, "rto_rate_pct": city_rto_rate(city) if city else None},
		"blacklisted": bool(bl),
	}

	# Build prompt and call AI
	censored = censor_order_for_ai(order_data, signals)
	if address_issues:
		censored["_pre_check_issues"] = address_issues

	prompt = _ORDER_PROMPT.format(
		order_data=_json.dumps(censored, indent=2, default=str),
		ors_results=ors_results_text,
		maps_results=maps_results_text,
		pre_check_issues="\n".join(address_issues) if address_issues else "None detected.",
		deep_evidence=_json.dumps(deep_evidence, indent=2, default=str),
	)

	raw = _call_ai(prompt)
	result = _parse_ai_json(raw)

	# Merge pre-check issues
	if address_issues:
		existing = result.get("address_issues", [])
		result["address_issues"] = address_issues + existing
		if not result.get("address_verified"):
			result["address_verified"] = False

	# Save AI results only (ORS/GMS data already saved by background tasks)
	frappe.db.set_value(
		"Sales Order",
		order_id,
		{
			"custom_ai_risk_score": result.get("score", 0),
			"custom_ai_risk_reasoning": result.get("reasoning", ""),
			"custom_ai_domain_scores": _json.dumps(
				result.get("domain_scores") or {}, default=str),
			"custom_ai_risk_analyzed_on": frappe.utils.now_datetime(),
			"custom_ai_risk_confidence": result.get("confidence", "low"),
		},
	)
	frappe.db.commit()

	return result


@tool
def score_order_risk(order_id: str) -> dict:
	"""Analyze fraud risk for a sales order using AI.
	Loads order data, censors personal info, fetches Maps verification,
	and calls the AI model. Saves a risk score (0-100) to the order."""
	return _do_score_order_risk(order_id)


@tool
def score_customer_risk(customer_id: str) -> dict:
	"""Analyze fraud risk for a customer using AI.
	Loads all their orders and addresses, censors personal info,
	and returns a risk score (0-100) with reasoning."""
	from shop.integrations.pii import censor_customer_for_ai

	customer = frappe.get_doc("Customer", customer_id)

	orders = frappe.get_all(
		"Sales Order",
		filters={"customer": customer_id},
		fields=["name", "grand_total", "docstatus", "custom_fraud_verdict", "custom_fraud_score"],
		order_by="creation desc",
		limit=20,
	)

	addresses = frappe.get_all(
		"Address",
		filters={"link_name": customer_id},
		fields=["address_line1", "address_line2", "city", "country"],
		limit=10,
	)

	customer_data = {
		"customer_name": customer.customer_name,
		"email": customer.email_id,
		"total_spent": sum(o.grand_total for o in orders if o.docstatus == 1),
		"order_count": len(orders),
		"orders": [
			{"name": o.name, "total": o.grand_total, "verdict": o.custom_fraud_verdict, "score": o.custom_fraud_score}
			for o in orders
		],
		"addresses": [
			{"line1": a.address_line1, "line2": a.address_line2, "city": a.city, "country": a.country}
			for a in addresses
		],
	}

	censored = censor_customer_for_ai(customer_data)
	prompt = _CUSTOMER_PROMPT.format(customer_data=_json.dumps(censored, indent=2, default=str))
	raw = _call_ai(prompt)
	result = _parse_ai_json(raw)

	return result
