"""IP Intelligence — free self-hosted checks.

Combines:
  • ip-api.com  (free, 45 req/min, no key) — VPN, proxy, datacenter, ISP, hosting
  • AbuseIPDB   (free tier, 1000 req/day)  — abuse score, Tor, reports
  • Tor exit node list (self-hosted, hourly refresh) — Tor detection

All results are cached for 24 hours per IP in a DocType to stay within
rate limits.  Call ``check_ip(ip)`` from the background fraud task.
"""

import json
import time
from datetime import datetime, timedelta

import frappe
from frappe.utils import cint, get_url, now_datetime

# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

_CACHE_TTL_HOURS = 24


def _cache_get(ip: str) -> dict | None:
	"""Return cached intel for *ip* or None if stale/missing."""
	if not ip:
		return None
	row = frappe.db.get_value(
		"Shop IP Cache",
		{"ip_address": ip},
		["name", "data_json", "checked_on"],
		as_dict=True,
	)
	if not row:
		return None
	if row.checked_on and (now_datetime() - row.checked_on) < timedelta(hours=_CACHE_TTL_HOURS):
		try:
			return json.loads(row.data_json)
		except Exception:
			return None
	return None


def _cache_set(ip: str, data: dict):
	if not ip:
		return
	name = frappe.db.get_value("Shop IP Cache", {"ip_address": ip})
	if name:
		frappe.db.set_value("Shop IP Cache", name, {
			"data_json": json.dumps(data),
			"checked_on": now_datetime(),
		})
	else:
		doc = frappe.get_doc({
			"doctype": "Shop IP Cache",
			"ip_address": ip,
			"data_json": json.dumps(data),
			"checked_on": now_datetime(),
		})
		doc.insert(ignore_permissions=True)


# ---------------------------------------------------------------------------
# ip-api.com  (free, no key, 45 req/min)
# ---------------------------------------------------------------------------

_IPAPI_URL = "http://ip-api.com/json/{ip}?fields=status,message,country,countryCode,regionName,city,isp,org,as,proxy,hosting,query"


def _fetch_ipapi(ip: str) -> dict:
	"""Query ip-api.com for VPN/proxy/hosting/ISP info."""
	import urllib.request
	import urllib.error

	try:
		req = urllib.request.Request(
			_IPAPI_URL.format(ip=ip),
			headers={"Accept": "application/json"},
		)
		with urllib.request.urlopen(req, timeout=5) as resp:
			raw = json.loads(resp.read())
		if raw.get("status") == "success":
			return {
				"country": raw.get("country", ""),
				"country_code": raw.get("countryCode", ""),
				"region": raw.get("regionName", ""),
				"city": raw.get("city", ""),
				"isp": raw.get("isp", ""),
				"org": raw.get("org", ""),
				"as": raw.get("as", ""),
				"proxy": bool(raw.get("proxy")),
				"hosting": bool(raw.get("hosting")),
			}
	except Exception:
		frappe.log_error(title=f"ip-api.com lookup failed for {ip}")
	return {}


# ---------------------------------------------------------------------------
# AbuseIPDB  (free tier: 1000 req/day, needs API key)
# ---------------------------------------------------------------------------

_ABUSEIPDB_URL = "https://api.abuseipdb.com/api/v2/check"


def _fetch_abuseipdb(ip: str) -> dict:
	"""Query AbuseIPDB for abuse score + Tor detection."""
	import urllib.request
	import urllib.error

	key = _get_abuseipdb_key()
	if not key:
		return {}

	try:
		req = urllib.request.Request(
			f"{_ABUSEIPDB_URL}?ipAddress={ip}&maxAgeInDays=90&verbose",
			headers={"Key": key, "Accept": "application/json"},
		)
		with urllib.request.urlopen(req, timeout=5) as resp:
			raw = json.loads(resp.read())

		data = raw.get("data", {})
		return {
			"abuse_score": cint(data.get("abuseConfidenceScore", 0)),
			"total_reports": cint(data.get("totalReports", 0)),
			"is_tor": bool(data.get("isTor")),
			"is_whitelisted": bool(data.get("isWhitelisted")),
			"usage_type": data.get("usageType", ""),
			"domain": data.get("domain", ""),
			"is_public": bool(data.get("isPublic")),
		}
	except urllib.error.HTTPError as e:
		# 429 = rate limit, don't log as error
		if e.code != 429:
			frappe.log_error(title=f"AbuseIPDB lookup failed for {ip}: {e.code}")
	except Exception:
		frappe.log_error(title=f"AbuseIPDB lookup failed for {ip}")
	return {}


def _get_abuseipdb_key() -> str:
	"""Return the AbuseIPDB API key from Shop Settings (encrypted field)."""
	try:
		s = frappe.get_doc("Shop Settings")
		return s.get_password("abuseipdb_api_key", raise_exception=False) or ""
	except Exception:
		return ""


# ---------------------------------------------------------------------------
# Tor exit node list  (self-hosted, downloaded hourly)
# ---------------------------------------------------------------------------

_TOR_URL = "https://check.torproject.org/torbulkexitlist"


def _refresh_tor_list() -> set[str]:
	"""Download the Tor exit node list and cache it in site_config."""
	import urllib.request

	try:
		req = urllib.request.Request(_TOR_URL, headers={"User-Agent": "PilotERP/1.0"})
		with urllib.request.urlopen(req, timeout=10) as resp:
			body = resp.read().decode("utf-8", errors="ignore")
		ips = {
			line.strip()
			for line in body.splitlines()
			if line.strip() and not line.startswith("#")
		}
		# Store in site_config for fast lookup
		site_config = frappe.get_site_config()
		site_config["_tor_exit_nodes"] = list(ips)
		site_config["_tor_refreshed"] = datetime.now().isoformat()
		frappe.db.set_default("_tor_exit_nodes", json.dumps(list(ips)))
		frappe.db.set_default("_tor_refreshed", site_config["_tor_refreshed"])
		frappe.db.commit()
		return ips
	except Exception:
		frappe.log_error(title="Failed to refresh Tor exit node list")
		return set()


def _get_tor_nodes() -> set[str]:
	"""Get the cached Tor exit node list, refreshing if older than 1 hour."""
	refreshed = frappe.db.get_default("_tor_refreshed")
	if refreshed:
		try:
			age = datetime.now() - datetime.fromisoformat(refreshed)
			if age < timedelta(hours=1):
				raw = frappe.db.get_default("_tor_exit_nodes")
				if raw:
					return set(json.loads(raw))
		except Exception:
			pass
	return _refresh_tor_list()


def is_tor_exit(ip: str) -> bool:
	"""Check if *ip* is a known Tor exit node."""
	if not ip:
		return False
	tor_nodes = _get_tor_nodes()
	return ip in tor_nodes


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def check_ip(ip: str) -> dict:
	"""Run all IP intelligence checks and return merged results.

	Returns a dict with keys:
	  proxy, hosting, isp, country_code, city, as_number,
	  abuse_score, total_reports, is_tor, is_whitelisted,
	  usage_type, abuse_domain
	"""
	if not ip:
		return {}

	cached = _cache_get(ip)
	if cached:
		return cached

	# ip-api.com (VPN/proxy/hosting/ISP)
	ipapi = _fetch_ipapi(ip)

	# AbuseIPDB (abuse score/Tor)
	abuse = _fetch_abuseipdb(ip)

	# Tor exit node list (self-hosted, free)
	tor_exit = is_tor_exit(ip)

	result = {
		"ip": ip,
		"proxy": ipapi.get("proxy", False),
		"hosting": ipapi.get("hosting", False),
		"isp": ipapi.get("isp", ""),
		"org": ipapi.get("org", ""),
		"country_code": ipapi.get("country_code", ""),
		"country": ipapi.get("country", ""),
		"region": ipapi.get("region", ""),
		"city": ipapi.get("city", ""),
		"as_number": ipapi.get("as", ""),
		# AbuseIPDB
		"abuse_score": abuse.get("abuse_score", 0),
		"total_reports": abuse.get("total_reports", 0),
		"is_tor": abuse.get("is_tor", False) or tor_exit,
		"is_whitelisted": abuse.get("is_whitelisted", False),
		"usage_type": abuse.get("usage_type", ""),
		"abuse_domain": abuse.get("domain", ""),
	}

	_cache_set(ip, result)
	return result
