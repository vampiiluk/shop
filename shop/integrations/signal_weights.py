# Fraud signal weights — editable in admin Fraud Weights page.
# Stored as JSON in Shop Settings.fraud_signal_weights (Code field).
# Missing keys fall back to these defaults. Negative values are bonuses
# that reduce the score.

import frappe

DEFAULT_SIGNAL_WEIGHTS = {
	# --- repeat fraud history ---
	"history_failed_rto_per": 15,
	"history_failed_rto_cap": 30,
	"history_cancelled_ratio_pts": 10,
	# --- blacklist / velocity / time ---
	"blacklist_hit": 40,
	"velocity_block": 40,
	"velocity_extra_per_order": 15,
	"velocity_extra_cap": 30,
	"fp_multiple_phones": 25,
	"risky_hour": 15,
	# --- fingerprint verification (Identification API) ---
	"fp_bot_tamper_replay": 40,
	"fp_suspect_high": 30,       # >= 0.8
	"fp_suspect_medium": 15,     # >= 0.5
	"fp_verify_failed": 30,
	"missing_fingerprint": 10,
	"ip_blocklist_hit": 20,
	"proxy_detected": 15,
	"incognito_privacy": 5,
	# --- address quality ---
	"address_short_line1": 15,
	"address_no_house_number": 10,
	"address_bad_pincode": 5,
	"address_unknown_city": 10,
	"address_missing_landmark": 15,
	"address_prior_failure": 30,
	# --- geocoding (ORS) ---
	"geo_not_found": 25,
	"geo_wrong_country": 30,
	"geo_city_mismatch": 20,
	"geo_no_house_number": 10,
	"geo_exact_match_bonus": -10,
	"geo_fallback_vague": 15,
	"landmark_corroborated_bonus": -10,
	"landmark_unmatched": 10,
	# --- city RTO rate ---
	"city_rto_high": 30,         # >= fraud_rto_high_pct
	"city_rto_medium": 15,       # >= fraud_rto_medium_pct
}


# UI metadata: group -> ordered [(key, label)]
WEIGHT_SCHEMA = [
	("Repeat history", [
		("history_failed_rto_per", "Per failed/RTO order"),
		("history_failed_rto_cap", "…capped at"),
		("history_cancelled_ratio_pts", ">50% cancelled bonus"),
	]),
	("Blacklist & velocity", [
		("blacklist_hit", "Blacklist hit"),
		("velocity_block", "Velocity limit reached"),
		("velocity_extra_per_order", "Per extra order/hour"),
		("velocity_extra_cap", "…capped at"),
		("fp_multiple_phones", "One device, many phones"),
	]),
	("Fingerprint verification", [
		("fp_bot_tamper_replay", "Bot / tampered / replayed"),
		("fp_suspect_high", "Suspect score ≥ 0.8"),
		("fp_suspect_medium", "Suspect score ≥ 0.5"),
		("fp_verify_failed", "Verification failed"),
		("missing_fingerprint", "COD order without fingerprint"),
		("ip_blocklist_hit", "IP blocklist hit"),
		("proxy_detected", "Proxy detected"),
		("incognito_privacy", "Incognito / privacy mode"),
	]),
	("Address quality", [
		("address_short_line1", "Street line too short"),
		("address_no_house_number", "No house/plot number"),
		("address_bad_pincode", "Malformed pincode"),
		("address_unknown_city", "City not in canonical list"),
		("address_missing_landmark", "Landmark missing"),
		("address_prior_failure", "Failed delivery at this address before"),
	]),
	("Geocoding", [
		("geo_not_found", "Address not found"),
		("geo_wrong_country", "Resolves to another country"),
		("geo_city_mismatch", "Stated city ≠ resolved area"),
		("geo_no_house_number", "No house number in match"),
		("geo_fallback_vague", "Vague/fallback match"),
		("geo_exact_match_bonus", "Exact match bonus (negative)"),
		("landmark_corroborated_bonus", "Landmark corroborated (negative)"),
		("landmark_unmatched", "Landmark filled but unmatched"),
	]),
	("City RTO & time", [
		("city_rto_high", "City RTO high threshold"),
		("city_rto_medium", "City RTO medium threshold"),
		("risky_hour", "Risky-hour order"),
	]),
]


def _flatten_schema():
	flat = []
	for entry in WEIGHT_SCHEMA:
		group, items = entry if isinstance(entry, tuple) else (entry, [])
		for item in items:
			flat.append((group, item))
	return flat


def get_weights(settings_doc=None) -> dict:
	"""Merged weight map: defaults overridden by stored JSON."""
	import json as _json

	settings_doc = settings_doc or frappe.get_cached_doc("Shop Settings")
	raw = getattr(settings_doc, "fraud_signal_weights", None)
	overrides = {}
	if raw:
		try:
			parsed = _json.loads(raw)
			if isinstance(parsed, dict):
				overrides = parsed
		except Exception:
			pass
	weights = dict(DEFAULT_SIGNAL_WEIGHTS)
	for key, value in overrides.items():
		if key in weights and isinstance(value, (int, float)) and not isinstance(value, bool):
			weights[key] = value
	return weights


def validate_weights_json(raw: str) -> str | None:
	"""Return cleaned JSON string or raise ValueError on bad content."""
	import json as _json

	if not raw or not raw.strip():
		return None
	parsed = _json.loads(raw)  # may raise ValueError
	if not isinstance(parsed, dict):
		raise ValueError("Must be a JSON object")
	valid = set(DEFAULT_SIGNAL_WEIGHTS)
	cleaned = {}
	for k, v in parsed.items():
		if k not in valid:
			continue
		if isinstance(v, bool) or not isinstance(v, (int, float)):
			continue
		cleaned[k] = v
	return _json.dumps(cleaned, indent=1) if cleaned else None
