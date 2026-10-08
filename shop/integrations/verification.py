"""Address verification cache — one unified ORS + GMS check per address.

Every unique delivery address (street line INCLUDING its nearest landmark)
gets ONE row in `Shop Address Verification`, keyed by an md5 hash of
line1+line2+city+pincode+landmark. Landmark is part of the address identity:
it is only used to authenticate/validate the address.

The record serves as cache (avoid re-scraping) and audit trail. Records can be
processed in bulk through `run_queue` (one GMS subprocess with -c N concurrent
browser tabs) or individually via order placement / manual re-verify.
TTL: 30 days for both ORS and GMS (configurable via Shop Settings).
"""

import csv
import io
import json

import frappe
from frappe import _
from frappe.utils import cint, get_datetime, now_datetime

TTL_DAYS = 30


# ---------------------------------------------------------------------------
# Cache keys
# ---------------------------------------------------------------------------

def address_hash(address: dict) -> str:
	"""Deprecated alias — kept so old imports keep working; delegates to geocoding."""
	from shop.integrations.geocoding import address_hash as _hash
	return _hash(address)


# ---------------------------------------------------------------------------
# Cache lookup / create
# ---------------------------------------------------------------------------

def get_or_create_verification(address: dict, source: str = "Order Placement") -> dict:
	"""Create the verification record for this address, or return the existing one.

	Deliberately does NOT commit. A commit here ends the caller's transaction
	and destroys any savepoint it took, which means a caller can no longer undo
	its own work: a bulk import that fails halfway keeps the rows written before
	the failure, and a test that creates data to score it cannot roll back. The
	verification row then outlives the thing it was created for, which is how
	orphan rows appear in the fraud dashboard for addresses no order uses.

	Callers own the boundary, and each one that needs the row visible to another
	process commits at that point:
	- order placement and re-evaluation commit immediately after linking the
	  order, before the verification work is queued;
	- the Address hook inherits the address save's own commit, so the row lands
	  with the address and disappears with it if the save is undone;
	- the queue's own seeding runs in-process, inside the queue job's
	  transaction.
	"""
	"""Lookup verification record by full-address hash (incl. landmark).

	Returns dict with keys: name, ors_status, gms_status, ors_result_json,
	gms_result_json, last_verified_on, is_ors_fresh, is_gms_fresh.
	"""
	from shop.integrations.geocoding import address_hash as _hash

	hkey = _hash(address)
	ttl = _get_ttl()

	existing = frappe.db.get_value(
		"Shop Address Verification",
		{"address_hash": hkey},
		["name", "ors_status", "gms_status", "ors_result_json", "gms_result_json",
		 "ors_verified_on", "gms_verified_on", "last_verified_on", "latitude", "longitude",
		 "linked_orders", "linked_phones", "linked_fingerprints", "source"],
		as_dict=True,
	)

	if existing:
		# The address was already on file, so the row keeps whatever source created
		# it. Without this an address a staff member entered by hand stays labelled
		# "Manual" forever, even once three orders have been placed to it - which
		# made the source filter report the opposite of what happened.
		#
		# "Manual" is the weakest provenance claim, so it yields to anything
		# stronger and never the reverse: an order arriving at an order-created
		# row must not downgrade it to look unused.
		if existing.source == "Manual" and source != "Manual":
			frappe.db.set_value(
				"Shop Address Verification", existing.name, {"source": source},
				update_modified=False,
			)
			existing.source = source

		# Each provider against its own stamp: one shared last_verified_on made a
		# stale Maps answer look fresh because ORS had just re-run.
		ors_stamp = existing.ors_verified_on or existing.last_verified_on
		gms_stamp = existing.gms_verified_on or existing.last_verified_on
		ors_fresh = (
			_is_fresh(ors_stamp, ttl) if existing.ors_status == "Complete" and ors_stamp else False
		)
		gms_fresh = (
			_is_fresh(gms_stamp, ttl) if existing.gms_status == "Complete" and gms_stamp else False
		)
		return {
			"name": existing.name,
			"ors_status": existing.ors_status,
			"gms_status": existing.gms_status,
			"ors_result_json": existing.ors_result_json,
			"gms_result_json": existing.gms_result_json,
			"latitude": existing.latitude,
			"longitude": existing.longitude,
			"linked_orders": existing.linked_orders or "",
			"linked_phones": existing.linked_phones or "",
			"linked_fingerprints": existing.linked_fingerprints or "",
			"is_ors_fresh": ors_fresh,
			"is_gms_fresh": gms_fresh,
		}

	doc = frappe.get_doc({
		"doctype": "Shop Address Verification",
		"address_hash": hkey,
		"address_line1": address.get("address_line1") or address.get("line1") or "",
		"city": address.get("city") or "",
		"landmark": address.get("landmark") or "",
		"country": address.get("country") or "",
		"province": address.get("province") or address.get("state") or "",
		"pincode": address.get("pincode") or "",
		"ors_status": "Skipped",
		"gms_status": "Disabled",
		"source": source,
	})
	try:
		doc.insert(ignore_permissions=True)
	except frappe.DuplicateEntryError:
		# The address hash is unique (patch v4). Two placements at one address
		# used to race past the lookup above and insert a second row, which
		# doubled the order counts in the fraud KPIs and let evaluate_risk read
		# either copy's risk score; the loser of the insert now re-reads the
		# winner's record.
		doc = frappe.get_doc("Shop Address Verification", {"address_hash": hkey})

	return {
		"name": doc.name,
		"ors_status": "Skipped",
		"gms_status": "Disabled",
		"ors_result_json": None,
		"gms_result_json": None,
		"latitude": None,
		"longitude": None,
		"linked_orders": "",
		"linked_phones": "",
		"linked_fingerprints": "",
		"is_ors_fresh": False,
		"is_gms_fresh": False,
	}


# ---------------------------------------------------------------------------
# Link order to verification record
# ---------------------------------------------------------------------------

def link_verification_to_order(verification_name: str, order_name: str, phone: str = "", fingerprint: str = "") -> None:
	"""Append order/phone/fingerprint to linked_* fields (comma-separated, deduped)."""
	# Read under a row lock. Two orders placed to the same address in the same
	# moment used to read the same list, each append its own, and the second
	# write silently dropped the first order's link - that order was then never
	# re-scored and sat in "Processing" for good.
	locked = frappe.db.sql(
		"""SELECT linked_orders, linked_phones, linked_fingerprints
			FROM `tabShop Address Verification` WHERE name = %s FOR UPDATE""",
		(verification_name,),
		as_dict=True,
	)
	ver = locked[0] if locked else None
	if not ver:
		return

	orders = _append_unique(ver.linked_orders or "", order_name)
	phones = _append_unique(ver.linked_phones or "", phone) if phone else ver.linked_phones or ""
	fps = _append_unique(ver.linked_fingerprints or "", fingerprint) if fingerprint else ver.linked_fingerprints or ""

	values = {"linked_orders": orders}
	if phone:
		values["linked_phones"] = phones
	if fingerprint:
		values["linked_fingerprints"] = fps

	frappe.db.set_value("Shop Address Verification", verification_name, values, update_modified=False)


def _append_unique(existing: str, value: str) -> str:
	"""Append value to comma-separated list if not already present."""
	items = [i.strip() for i in existing.split(",") if i.strip()]
	if value and value not in items:
		items.append(value)
	return ", ".join(items)


# ---------------------------------------------------------------------------
# ORS verification
# ---------------------------------------------------------------------------

def _ors_values(summary: dict | None, home_countries) -> dict:
	"""The record fields for one ORS result.

	One place decides whether a geocode is stored, because the single-record path
	and the queue's batch path both write these fields and they had drifted: the
	batch wrote `Complete` and the coordinates unconditionally, so fixing the
	single path alone still left every queued address with the provider's
	mistake pinned to it.

	A fallback match, or one in a country the shop does not serve, is stored as a
	rejection - the raw response is kept so it can be read, but the coordinates
	are cleared rather than left as they were, since a stale pin from an earlier
	run is how a wrong location outlives the lookup that found it. The status is
	not Complete, so freshness fails and the queue retries instead of trusting it.
	"""
	import json as _json

	from shop.integrations.geocoding import geocode_is_usable

	usable, reason = geocode_is_usable(summary, home_countries)
	if not usable:
		summary["accepted"] = False
		summary["rejected_because"] = reason
		return {
			"ors_status": "Failed",
			"ors_result_json": _json.dumps(summary, default=str),
			"ors_confidence": summary.get("confidence"),
			"ors_match_type": summary.get("match_type", ""),
			"latitude": None,
			"longitude": None,
			"ors_verified_on": None,
		}

	summary["accepted"] = True
	summary.pop("rejected_because", None)
	return {
		"ors_status": "Complete",
		"ors_result_json": _json.dumps(summary, default=str),
		"ors_confidence": summary.get("confidence"),
		"ors_match_type": summary.get("match_type", ""),
		"latitude": summary.get("lat"),
		"longitude": summary.get("lng"),
		"ors_verified_on": now_datetime(),
		"last_verified_on": now_datetime(),
	}


REVIEW_STATES = ("Unreviewed", "Verified", "Rejected", "Needs Lookup")


def set_review_state(verification_name: str, state: str, note: str = "") -> dict:
	"""Record a human's judgement about an address.

	Setting this to Verified takes the address out of the fraud maths, which makes
	re-deriving the orders it already held the other half of the job: an order
	that was pushed to Advance Required by an address nobody had ever looked at
	stays that way until someone rescores it.

	Re-evaluation runs on *every* state change, not only on Verified. Only
	re-running on the way down would make the override a one-way ratchet - you
	could talk an order out of Advance Required by verifying its address, but
	revoking that judgement would leave the order on the score it should no longer
	be carrying. The judgement and the consequences of it have to move together.

	The review fields are separate from everything the pipeline writes, so a
	re-verification cannot quietly clear a human's judgement - which is the whole
	point of it, and the reason it does not live in `status`.
	"""
	if state not in REVIEW_STATES:
		frappe.throw(_("Unknown review state"))
	if not frappe.db.exists("Shop Address Verification", verification_name):
		frappe.throw(_("Verification record not found"))

	values = {
		"review_state": state,
		"reviewed_on": now_datetime(),
		"review_note": (note or "").strip()[:500],
	}
	# Clearing back to Unreviewed drops the attribution too - an unreviewed
	# record has no reviewer, and leaving one there implies someone vouched for
	# it and then stopped caring.
	values["reviewed_by"] = (
		frappe.session.user if state != "Unreviewed" else None
	)

	frappe.db.set_value("Shop Address Verification", verification_name, values)
	frappe.db.commit()

	from shop.integrations.fraud import reevaluate_order_for_verification

	reevaluate_order_for_verification(verification_name)
	frappe.db.commit()

	return {
		"name": verification_name,
		"review_state": state,
		"orders_rescored": len(_linked_order_names(verification_name)),
	}


def _linked_order_names(verification_name: str) -> list:
	raw = frappe.db.get_value("Shop Address Verification", verification_name, "linked_orders")
	return [o.strip() for o in (raw or "").split(",") if o.strip()]


def run_ors_verification(verification_name: str) -> dict:
	"""Call ORS for a verification record. Update results + status."""
	from shop.integrations.fraud import home_country_codes
	from shop.integrations.geocoding import _call_ors, _ors_key, _summarize_ors

	ver = frappe.db.get_value(
		"Shop Address Verification", verification_name,
		["name", "address_line1", "city", "landmark", "country", "pincode"],
		as_dict=True,
	)
	if not ver:
		return {"error": "Verification record not found"}

	frappe.db.set_value("Shop Address Verification", verification_name, {"ors_status": "Pending"})
	frappe.db.commit()

	settings = frappe.get_cached_doc("Shop Settings")
	api_key = _ors_key(settings)
	if not api_key:
		frappe.db.set_value("Shop Address Verification", verification_name, {"ors_status": "Failed"})
		frappe.db.commit()
		return {"error": "No ORS API key configured"}

	full_address = ", ".join(
		p.strip()
		for p in (
			ver.address_line1,
			ver.landmark,
			ver.city,
			ver.pincode,
			ver.country or "Pakistan",
		)
		if (p or "").strip()
	)

	payload = _call_ors(full_address, api_key)
	summary = _summarize_ors(payload)

	if summary is None:
		frappe.db.set_value("Shop Address Verification", verification_name, {"ors_status": "Failed"})
		frappe.db.commit()
		return {"error": "ORS API call failed"}

	frappe.db.set_value(
		"Shop Address Verification", verification_name,
		_ors_values(summary, home_country_codes(settings)),
	)
	frappe.db.commit()

	return summary


# ---------------------------------------------------------------------------
# Freshness check
# ---------------------------------------------------------------------------

def is_ors_fresh(verification_name: str) -> bool:
	"""Check if ORS result is within TTL.

	Measured from ors_verified_on, not last_verified_on: the two providers run
	independently, so Maps answering today used to make a six-week-old geocode
	look fresh. Falls back to last_verified_on for rows written before the
	per-provider timestamps existed.
	"""
	ver = frappe.db.get_value(
		"Shop Address Verification", verification_name,
		["ors_status", "ors_verified_on", "last_verified_on"],
		as_dict=True,
	)
	if not ver or ver.ors_status != "Complete":
		return False
	stamp = ver.ors_verified_on or ver.last_verified_on
	if not stamp:
		return False
	return _is_fresh(stamp, _get_ttl())


def is_gms_fresh(verification_name: str) -> bool:
	"""Check if GMS result is within TTL. Same per-provider stamp as ORS above."""
	ver = frappe.db.get_value(
		"Shop Address Verification", verification_name,
		["gms_status", "gms_verified_on", "last_verified_on"],
		as_dict=True,
	)
	if not ver or ver.gms_status != "Complete":
		return False
	stamp = ver.gms_verified_on or ver.last_verified_on
	if not stamp:
		return False
	return _is_fresh(stamp, _get_ttl())


def _is_fresh(last_verified, ttl_days: int) -> bool:
	if not last_verified:
		return False
	return (now_datetime() - get_datetime(last_verified)).days < ttl_days


def _get_ttl() -> int:
	"""Read TTL from Shop Settings, fallback to default."""
	try:
		return cint(frappe.db.get_single_value("Shop Settings", "geocode_cache_ttl")) or TTL_DAYS
	except Exception:
		return TTL_DAYS


# ---------------------------------------------------------------------------
# Mirror summary onto ERPNext Address records
# ---------------------------------------------------------------------------

def sync_address_summary(verification_name: str) -> int:
	"""Copy verification summary fields onto every ERPNext Address whose
	custom_address_hash matches this record. Returns number of addresses updated."""
	ver = frappe.db.get_value(
		"Shop Address Verification", verification_name,
		["address_hash", "status", "address_risk_score", "ors_confidence", "ors_status",
		 "latitude", "longitude", "gms_result_count", "last_verified_on"],
		as_dict=True,
	)
	if not ver or not ver.address_hash:
		return 0

	names = frappe.get_all(
		"Address",
		filters={"custom_address_hash": ver.address_hash},
		pluck="name",
	)
	if not names:
		return 0

	# Only a completed geocode has coordinates worth copying. A failed ors_status
	# means the lookup produced nothing usable, and writing whatever the column
	# happens to hold would stamp a stale pin onto the customer's saved address.
	have_location = ver.ors_status == "Complete" and ver.latitude is not None

	frappe.db.set_value("Address", {"name": ["in", names]}, {
		"custom_verification_status": ver.status,
		"custom_address_risk_score": ver.address_risk_score,
		"custom_ors_confidence": ver.ors_confidence,
		"custom_latitude": ver.latitude if have_location else None,
		"custom_longitude": ver.longitude if have_location else None,
		"custom_gms_result_count": ver.gms_result_count or 0,
		"custom_last_verified_on": ver.last_verified_on,
		"custom_address_verification": verification_name,
	}, update_modified=False)
	return len(names)


# ---------------------------------------------------------------------------
# Bulk verification queue
# ---------------------------------------------------------------------------

QUEUE_LOCK_KEY = "shop_verification_queue_running"
# Long enough for a full batch (draining 50 items with Maps lookups takes
# minutes), short enough that a dead worker cannot silence the queue for long.
QUEUE_LOCK_TTL = 30 * 60


def queue_status() -> dict:
	"""Is the queue worker running, and how many items still need work?"""
	ttl = _get_ttl()
	gms_enabled = _gms_enabled()
	ors_enabled = _ors_enabled()
	rows = frappe.db.sql(
		f"""SELECT name, status, ors_status, gms_status, last_verified_on
		FROM `tabShop Address Verification`
		WHERE status IS NULL OR status NOT IN ('Complete')
		   OR last_verified_on IS NULL
		   OR last_verified_on < DATE_SUB(NOW(), INTERVAL {int(ttl)} DAY)
		LIMIT 5000""",
		as_dict=True,
	)
	pending = sum(1 for r in rows if _needs_work(r, ttl, gms_enabled, ors_enabled))
	return {
		"running": bool(frappe.cache().get_value(QUEUE_LOCK_KEY)),
		"pending": pending,
	}


def _gms_enabled() -> bool:
	settings_doc = frappe.get_cached_doc("Shop Settings")
	if not getattr(settings_doc, "gms_enabled", True):
		return False
	return (getattr(settings_doc, "maps_provider", None) or "Google Maps Scraper") == "Google Maps Scraper"


def _ors_enabled() -> bool:
	settings_doc = frappe.get_cached_doc("Shop Settings")
	if not getattr(settings_doc, "ors_enabled", True):
		return False
	return bool(getattr(settings_doc, "ors_api_key", None))


def _needs_work(row, ttl_days: int, gms_enabled: bool, ors_enabled: bool = True) -> bool:
	if getattr(row, "status", None) == "Queued":
		return True
	if ors_enabled and row.ors_status != "Complete":
		return True
	if gms_enabled and row.gms_status != "Complete":
		return True
	if not ors_enabled and not gms_enabled:
		# Both disabled — nothing to do
		return False
	if not row.last_verified_on:
		return True
	return (now_datetime() - get_datetime(row.last_verified_on)).days >= ttl_days


def _seed_missing_rows(limit: int = 500) -> int:
	"""Create Pending verification rows for addresses whose hash has none
	(e.g. after the landmark changed or a new address was saved in Desk).

	The old version pulled every Address row - and a Python set of every
	verification hash - into memory on each queue tick, and again inside the
	manager's "run queue" click. This asks the database for only the rows with
	no match, capped at what one pass can actually work through.
	"""
	rows = frappe.db.sql(
		"""
		SELECT a.address_line1, a.address_line2, a.city, a.country,
		       a.pincode, a.custom_landmark
		FROM `tabAddress` a
		LEFT JOIN `tabShop Address Verification` v ON v.address_hash = a.custom_address_hash
		WHERE a.disabled = 0 AND a.custom_address_hash IS NOT NULL AND a.custom_address_hash != ''
		  AND v.name IS NULL
		ORDER BY a.modified ASC
		LIMIT %s
		""",
		(limit,),
		as_dict=True,
	)
	for addr in rows:
		get_or_create_verification(
			{
				"address_line1": addr.address_line1,
				"address_line2": addr.address_line2,
				"city": addr.city,
				"country": addr.country,
				"pincode": addr.pincode,
				"landmark": addr.custom_landmark,
			},
			source="Manual",
		)
	return len(rows)


def get_queue_items(limit: int | None = None) -> list[frappe._dict]:
	"""Verification records that still need ORS/GMS work or are stale."""
	_seed_missing_rows()
	ttl = _get_ttl()
	gms_enabled = _gms_enabled()
	ors_enabled = _ors_enabled()
	limit = cint(limit) or 100
	rows = frappe.db.sql(
		f"""SELECT name, address_line1, city, landmark, country, province, pincode,
			status, ors_status, gms_status, last_verified_on
		FROM `tabShop Address Verification`
		WHERE status IS NULL OR status NOT IN ('Complete')
		   OR last_verified_on IS NULL
		   OR last_verified_on < DATE_SUB(NOW(), INTERVAL {int(ttl)} DAY)
		ORDER BY modified ASC
		LIMIT %s""",
		(limit,),
		as_dict=True,
	)
	return [r for r in rows if _needs_work(r, ttl, gms_enabled, ors_enabled)]


def run_queue(limit: int | None = None) -> dict:
	"""Process the verification backlog in bulk.

	ORS calls run in a thread pool; GMS runs as ONE subprocess handling all
	queries with `-c N` concurrent browser tabs (N = Shop Settings.gms_concurrency).
	Returns a stats dict."""
	import concurrent.futures

	lock = frappe.cache()
	if lock.get_value(QUEUE_LOCK_KEY):
		return {"queued": 0, "running": True, "message": "Queue already running"}
	# With a TTL: a worker killed mid-run (OOM, restart) used to leave this flag
	# set forever, after which the cron saw "running" and never enqueued another
	# pass - the verification queue died quietly and every fraud score stayed
	# provisional until someone cleared the cache by hand.
	lock.set_value(QUEUE_LOCK_KEY, 1, expires_in_sec=QUEUE_LOCK_TTL)
	try:
		items = [r for r in get_queue_items(limit=limit)]
		stats = {"queued": len(items), "completed": 0, "partial": 0, "failed": 0}
		if not items:
			return stats
		result = _verify_records(items)
		stats.update(result)
		return stats
	finally:
		try:
			lock.delete_value(QUEUE_LOCK_KEY)
		except Exception:
			pass


def start_queue_job(limit: int | None = None) -> str:
	"""Enqueue the bulk queue as a long background job. Returns job_id."""
	return frappe.enqueue(
		"shop.integrations.verification._queue_job",
		queue="long",
		timeout=3600,
		limit=limit,
	)


def _queue_job(limit: int | None = None) -> None:
	run_queue(limit=limit)


def scheduled_queue_run() -> None:
	"""Cron entry (fires every 10 and every 20 minutes). Drains up to 50
	queue items when the Shop Settings cadence says this slot is due."""
	try:
		st = frappe.get_cached_doc("Shop Settings")
		schedule = getattr(st, "queue_schedule", None) or "Every 20 Minutes"
	except Exception:
		schedule = "Every 20 Minutes"

	minute = frappe.utils.now_datetime().minute
	if schedule == "Every 10 Minutes":
		due = minute % 10 == 0
	elif schedule == "Hourly":
		due = minute < 10
	else:
		due = minute % 20 == 0
	if not due:
		return

	# Both crons can fire within the same minute - keep only one runner.
	if not frappe.cache().set_if_not_exists("shop_queue_tick_lock", 1):
		return
	frappe.cache().expire("shop_queue_tick_lock", 540)

	status = queue_status()
	if status.get("pending") and not status.get("running"):
		start_queue_job(limit=50)


def reverify_address(verification_name: str) -> dict:
	"""Flag a single record as queued. It runs when Process Queue is pressed."""
	if not frappe.db.exists("Shop Address Verification", verification_name):
		frappe.throw(_("Verification record not found"))
	frappe.db.set_value(
		"Shop Address Verification", verification_name,
		{"status": "Queued"}, update_modified=False,
	)
	frappe.db.commit()
	return {"status": "queued", "name": verification_name}


def bulk_reverify(filters: dict = None, providers: str = "both") -> str:
	"""Enqueue re-verification of everything matching filters (or all).
	Filters are best-effort; the queue skips anything already fresh."""
	del filters  # kept for API compatibility
	return start_queue_job(limit=None)


def _propagate_to_orders(ver_name: str, gms_results, gms_enabled: bool) -> None:
	"""Mirror GMS results onto linked Sales Orders (checkout no longer runs
	verification inline - the queue fills these in after the fact)."""
	import json as _json
	from shop.agent.tools import _format_maps_results

	try:
		linked = frappe.db.get_value(
			"Shop Address Verification", ver_name, "linked_orders") or ""
	except Exception:
		return
	names = [s.strip() for s in linked.split(",") if s.strip()]
	if not names:
		return

	maps_status = (
		"Disabled" if not gms_enabled
		else ("Failed" if gms_results is None else "Complete")
	)
	values = {
		"custom_ai_maps_json": _json.dumps(gms_results, default=str) if gms_results else "",
		"custom_ai_maps_results": _format_maps_results(gms_results) if gms_results else "",
		"custom_ai_maps_status": maps_status,
	}
	for so in names:
		if frappe.db.exists("Sales Order", so):
			frappe.db.set_value("Sales Order", so, values)


def _verify_records(items: list[frappe._dict]) -> dict:
	"""Core pipeline shared by run_queue and single re-verify."""
	import concurrent.futures
	import json as _json

	from shop.agent.tools import (
		_format_maps_results,
		_search_google_maps_batch_by_id,
	)
	from shop.integrations.fraud import compute_verification_risk, home_country_codes

	settings_doc = frappe.get_cached_doc("Shop Settings")
	gms_enabled = _gms_enabled()
	ors_enabled = _ors_enabled()
	depth = cint(getattr(settings_doc, "gms_depth", 0)) or 5
	concurrency = min(max(cint(getattr(settings_doc, "gms_concurrency", 0)) or 4, 1), 8)

	stats = {"completed": 0, "partial": 0, "failed": 0}
	if not items:
		return stats

	ors_out: dict = {}

	for r in items:
		frappe.db.set_value(
			"Shop Address Verification", r.name,
			{"status": "Pending"}, update_modified=False,
		)
	frappe.db.commit()

	# --- Stage 1: ORS geocoding ---
	# Threads only do pure HTTP: frappe's DB connection has no site context
	# inside pool threads, so every frappe.db write happens on the main thread.
	if ors_enabled:
		from shop.integrations.geocoding import _call_ors, _ors_key, _summarize_ors

		api_key = _ors_key(settings_doc)

		def _do_ors(rec):
			full_address = ", ".join(
				p.strip()
				for p in (rec.address_line1, rec.landmark, rec.city, rec.pincode,
					rec.country or "Pakistan")
				if p and p.strip()
			)
			try:
				return rec.name, _summarize_ors(_call_ors(full_address, api_key))
			except Exception:
				return rec.name, None

		with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(items), concurrency)) as pool:
			ors_out = dict(pool.map(_do_ors, items))

		for r in items:
			summary = ors_out.get(r.name)
			if summary is None:
				frappe.db.set_value(
					"Shop Address Verification", r.name,
					{"ors_status": "Failed"}, update_modified=False,
				)
				continue
			frappe.db.set_value(
				"Shop Address Verification", r.name,
				_ors_values(summary, home_country_codes(settings_doc)),
				update_modified=False,
			)
		frappe.db.commit()
	else:
		# ORS disabled — mark all as skipped
		for r in items:
			frappe.db.set_value(
				"Shop Address Verification", r.name,
				{"ors_status": "Disabled"}, update_modified=False,
			)
		frappe.db.commit()

	# --- Stage 2: GMS — one subprocess, N concurrent browser tabs ---
	gms_by_id: dict[str, list[dict]] = {}
	if gms_enabled:
		batch = []
		for r in items:
			q = ", ".join(
				p for p in (r.address_line1, r.landmark, r.city, r.pincode, r.country or "Pakistan")
				if p and p.strip()
			)
			if q:
				batch.append((r.name, q))
		if batch:
			gms_by_id = _search_google_maps_batch_by_id(
				batch, depth=depth, concurrency=concurrency,
			) or {}

	# --- Stage 3: persist results + combined risk score ---
	for r in items:
		try:
			ver = frappe.db.get_value(
				"Shop Address Verification", r.name,
				["ors_result_json"], as_dict=True,
			)
			ors_result = None
			if ver and ver.ors_result_json:
				try:
					ors_result = _json.loads(ver.ors_result_json)
				except Exception:
					ors_result = None

			gms_results = gms_by_id.get(r.name)
			if not gms_enabled:
				frappe.db.set_value("Shop Address Verification", r.name, {"gms_status": "Disabled"})
			elif gms_results is None:
				frappe.db.set_value("Shop Address Verification", r.name, {
					"gms_status": "Failed",
					"gms_result_json": "",
					"gms_result_text": "",
					"gms_result_count": 0,
				})
			else:
				text = _format_maps_results(gms_results)
				frappe.db.set_value("Shop Address Verification", r.name, {
					"gms_status": "Complete",
					"gms_result_json": _json.dumps(gms_results, default=str),
					"gms_result_text": text,
					"gms_result_count": len(gms_results),
					"gms_verified_on": now_datetime(),
					"last_verified_on": now_datetime(),
				})

			address = {
				"address_line1": r.address_line1 or "",
				"city": r.city or "",
				"landmark": r.landmark or "",
				"country": r.country or "",
				"state": r.province or "",
				"pincode": r.pincode or "",
			}
			risk = compute_verification_risk(
				address,
				ors_result=ors_result,
				gms_results=gms_results,
				settings_doc=settings_doc,
			)
			ors_summary = ors_out.get(r.name)
			# "Returned something" is not "verified": a fallback or wrong-country
			# match comes back non-None and would otherwise mark the record
			# Complete, which is what made this look like a passed check.
			ors_ok = bool(
				ors_enabled and ors_summary is not None and not ors_summary.get("rejected_because")
			)
			gms_ok = (not gms_enabled) or (gms_results is not None)
			vstatus = "Complete" if (ors_ok and gms_ok) else ("Partial" if (ors_ok or gms_ok) else "Failed")

			frappe.db.set_value("Shop Address Verification", r.name, {
				"status": vstatus,
				"address_risk_status": risk["status"],
				"address_risk_score": risk["score"],
				"address_risk_json": _json.dumps(risk["details"], default=str),
				"address_risk_breakdown": _json.dumps(risk.get("breakdown") or {}, default=str),
			})
			_propagate_to_orders(r.name, gms_results, gms_enabled)
			sync_address_summary(r.name)
			frappe.db.commit()

			# Verification attempt finished - refresh fraud score/verdict
			# for every linked order (they were provisional until now).
			try:
				from shop.integrations.fraud import reevaluate_order_for_verification
				reevaluate_order_for_verification(r.name)
			except Exception:
				frappe.log_error(title=f"Fraud re-evaluation hook failed for {r.name}")

			if vstatus == "Complete":
				stats["completed"] += 1
			elif vstatus == "Partial":
				stats["partial"] += 1
			else:
				stats["failed"] += 1
		except Exception:
			frappe.log_error(title=f"Queue finalize failed for {r.name}")
			stats["failed"] += 1

	return stats


# ---------------------------------------------------------------------------
# Export CSV
# ---------------------------------------------------------------------------

def export_verifications_csv(filters: dict = None) -> str:
	"""Enqueue CSV export background job. Returns job_id."""
	return frappe.enqueue(
		"shop.integrations.verification._export_csv_job",
		queue="short",
		timeout=120,
		filters=filters,
	)


def _export_csv_job(filters: dict = None) -> None:
	"""Background job: generate CSV file for download."""
	flt = filters or {}
	cond = "1=1"
	params = []

	if flt.get("city"):
		cond += " AND city = %s"
		params.append(flt["city"])
	if flt.get("ors_status"):
		cond += " AND ors_status = %s"
		params.append(flt["ors_status"])
	if flt.get("gms_status"):
		cond += " AND gms_status = %s"
		params.append(flt["gms_status"])
	if flt.get("source"):
		cond += " AND source = %s"
		params.append(flt["source"])

	rows = frappe.db.sql(
		f"""SELECT address_line1, city, landmark, country, pincode,
			latitude, longitude, ors_status, ors_confidence, ors_match_type,
			ors_result_json, gms_status, gms_result_count, gms_result_text,
			gms_result_json, source, linked_orders, linked_phones,
			last_verified_on
		FROM `tabShop Address Verification`
		WHERE {cond}
		ORDER BY city, address_line1
		LIMIT 5000""",
		tuple(params),
		as_dict=True,
	)

	# The risk columns are exported too: without them a round-trip through this
	# exporter produced rows that looked verified but carried no score, and the
	# fraud engine had nothing to read from them.
	headers = [
		"address_line1", "city", "landmark", "country", "pincode",
		"latitude", "longitude", "ors_status", "ors_confidence", "ors_match_type",
		"ors_result_json", "gms_status", "gms_result_count", "gms_result_text",
		"gms_result_json", "address_risk_status", "address_risk_score",
		"address_risk_json", "source", "linked_orders", "linked_phones",
		"last_verified_on",
	]

	buf = io.StringIO()
	writer = csv.DictWriter(buf, fieldnames=headers)
	writer.writeheader()
	for row in rows:
		writer.writerow({k: (str(row[k]) if row[k] is not None else "") for k in headers})

	# Save to files
	filename = f"verifications_export_{frappe.utils.now_datetime().strftime('%Y%m%d_%H%M%S')}.csv"
	file_path = frappe.get_site_path("private", "files", filename)
	with open(file_path, "w", newline="") as f:
		f.write(buf.getvalue())


def get_export_status() -> dict:
	"""Check if most recent export file exists, return URL."""
	import glob as _glob

	pattern = frappe.get_site_path("private", "files", "verifications_export_*.csv")
	files = sorted(_glob.glob(pattern), reverse=True)
	if not files:
		return {"status": "empty", "url": None}

	latest = files[0]
	filename = latest.rsplit("/", 1)[-1]
	# The export holds customer addresses, so it is written under private/files
	# and must not be linked as a public /files/ URL: that path cannot resolve
	# it, and "fixing" it by moving the file into public/ would publish the
	# customer addresses. Managers fetch it through the guarded download
	# endpoint instead.
	return {
		"status": "complete",
		"filename": filename,
		"url": None,
		"message": "Use the Download export button (manager-only) to fetch this file.",
	}


# ---------------------------------------------------------------------------
# Import CSV (round-trip: import exported CSV)
# ---------------------------------------------------------------------------

def import_verified_csv(csv_content: str) -> dict:
	"""Parse exported CSV, upsert verification records. No background jobs.

	All imported records are status=Complete (data already verified).
	Returns {imported, updated, skipped, errors}.
	"""
	reader = csv.DictReader(io.StringIO(csv_content))
	imported = 0
	updated = 0
	skipped = 0
	errors = []

	for i, row in enumerate(reader):
		try:
			addr_line1 = (row.get("address_line1") or "").strip()
			city = (row.get("city") or "").strip()
			if not addr_line1 or not city:
				skipped += 1
				continue

			address = {
				"address_line1": addr_line1,
				"city": city,
				"landmark": (row.get("landmark") or "").strip(),
				"country": (row.get("country") or "").strip(),
				"pincode": (row.get("pincode") or "").strip(),
			}
			hkey = address_hash(address)

			existing = frappe.db.get_value("Shop Address Verification", {"address_hash": hkey}, "name")

			values = {
				"address_hash": hkey,
				"address_line1": addr_line1,
				"city": city,
				"landmark": address["landmark"],
				"country": address["country"],
				"pincode": address["pincode"],
				"latitude": _safe_float(row.get("latitude")),
				"longitude": _safe_float(row.get("longitude")),
				"ors_status": row.get("ors_status") or "Complete",
				"ors_confidence": _safe_float(row.get("ors_confidence")),
				"ors_match_type": (row.get("ors_match_type") or "").strip(),
				"ors_result_json": row.get("ors_result_json") or "",
				"gms_status": row.get("gms_status") or "Complete",
				"gms_result_count": cint(row.get("gms_result_count")),
				"gms_result_text": row.get("gms_result_text") or "",
				"gms_result_json": row.get("gms_result_json") or "",
				"source": "Bulk Import",
				"linked_orders": row.get("linked_orders") or "",
				"linked_phones": row.get("linked_phones") or "",
				"last_verified_on": now_datetime(),
			}

			from shop.integrations.fraud import compute_verification_risk
			import json as _json

			# An imported record carrying no risk score looks complete and
			# contributes nothing: evaluate_risk reads a missing address_risk_json
			# as "verification unavailable" and adds no signal at all. Compute it
			# from the data the row was imported with, exactly as the queue would.
			risk = compute_verification_risk(
				address,
				ors_result=_safe_json(row.get("ors_result_json")),
				gms_results=(
					_safe_json(row.get("gms_result_json")) if (row.get("gms_status") or "") == "Complete" else None
				),
			)
			values["address_risk_status"] = risk["status"]
			values["address_risk_score"] = risk["score"]
			values["address_risk_json"] = _json.dumps(risk["details"], default=str)
			values["address_risk_breakdown"] = _json.dumps(risk.get("breakdown") or {}, default=str)

			if existing:
				frappe.db.set_value("Shop Address Verification", existing, values, update_modified=False)
				updated += 1
			else:
				try:
					doc = frappe.get_doc({"doctype": "Shop Address Verification", **values})
					doc.insert(ignore_permissions=True)
					imported += 1
				except frappe.DuplicateEntryError:
					frappe.db.set_value(
						"Shop Address Verification",
						frappe.db.get_value("Shop Address Verification", {"address_hash": hkey}, "name"),
						values,
						update_modified=False,
					)
					updated += 1

			if (imported + updated) % 100 == 0:
				frappe.db.commit()
		except Exception as e:
			errors.append(f"Row {i+2}: {str(e)}")
			if len(errors) > 20:
				break

	frappe.db.commit()
	return {"imported": imported, "updated": updated, "skipped": skipped, "errors": errors}


def _safe_json(raw):
	"""Parse a JSON column from a CSV import without aborting the row."""
	if not raw:
		return None
	try:
		return _json.loads(raw)
	except Exception:
		return None


def _safe_float(val) -> float | None:
	try:
		if val is None or str(val).strip() == "":
			return None
		return float(val)
	except (ValueError, TypeError):
		return None


# ---------------------------------------------------------------------------
# Address doc_events hook
# ---------------------------------------------------------------------------

def on_address_update(doc, method: str | None = None) -> None:
	"""doc_events hook (Address on_update): keep custom_address_hash in sync
	with the address + landmark, and make sure a verification record exists so
	the bulk queue can pick the address up."""
	from shop.integrations.geocoding import address_hash

	addr = {
		"address_line1": doc.address_line1,
		"address_line2": doc.address_line2,
		"city": doc.city,
		"pincode": doc.pincode,
		# Both were missing here, and the verification record has a column for
		# each. Without them user_country_mismatch and province_mismatch could
		# never fire on this path - the main one, since it is how a saved
		# address gets verified - so a customer naming the wrong country or
		# province was scored as clean.
		"country": doc.country,
		"state": doc.state,
		"landmark": doc.get("custom_landmark"),
	}
	hkey = address_hash(addr)

	if doc.get("custom_address_hash") != hkey:
		frappe.db.set_value("Address", doc.name, "custom_address_hash", hkey,
			update_modified=False)

	if not frappe.db.exists("Shop Address Verification", {"address_hash": hkey}):
		try:
			get_or_create_verification(addr, source="Manual")
		except Exception:
			frappe.log_error(title=f"Verification ensure failed for Address {doc.name}")
