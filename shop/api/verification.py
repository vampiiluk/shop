"""Verification dashboard API endpoints."""

import frappe
from frappe import _
from frappe.utils import add_days, cint, nowdate

from shop.api import only_managers


@frappe.whitelist()
def get_verifications(filters=None, limit=50, offset=0):
	"""Paginated list of Shop Address Verification records."""
	only_managers()
	flt = filters if isinstance(filters, dict) else {}
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
	if flt.get("search"):
		cond += " AND (address_line1 LIKE %s OR landmark LIKE %s OR city LIKE %s)"
		s = f"%{flt['search']}%"
		params.extend([s, s, s])
	if flt.get("needs_attention"):
		# A provider that is enabled but did not produce something usable. The
		# per-status dropdowns cannot express this: a fallback match and a dropped
		# connection both land on "Failed", and one is the geocoder's fault while
		# the other is worth looking at. This is the set to re-run after an
		# outage, and it was previously invisible without opening every record.
		cond += " AND (ors_status IN ('Failed', 'Pending') OR gms_status IN ('Failed', 'Pending'))"

	total = frappe.db.sql(
		f"SELECT COUNT(*) FROM `tabShop Address Verification` WHERE {cond}",
		tuple(params),
	)[0][0]

	rows = frappe.db.sql(
		f"""SELECT name, address_hash, address_line1, city, landmark, country, pincode,
			latitude, longitude, status, ors_status, gms_status, gms_result_count,
			address_risk_score, address_risk_status,
			-- ors_status alone cannot tell "the call failed" from "the geocode was
			-- rejected", which is why the ORS column used to show a bare red
			-- "Failed" for a record the provider had answered perfectly well with
			-- the wrong answer. rejected_because is in the stored JSON only.
			CASE WHEN ors_status = 'Failed'
				AND ors_result_json LIKE '%%rejected_because%%' THEN 1 ELSE 0 END AS ors_rejected,
			-- Guarded on the leading brace: JSON_EXTRACT raises on empty text, and
			-- ors_result_json is blank on records that never reached a provider, so
			-- an unguarded extract would break the whole list, not one row. LEFT()
			-- rather than a LIKE, because this query is parameterised and the driver
			-- applies its own percent-formatting to it, comments included.
			CASE WHEN LEFT(ors_result_json, 1) = '{{'
				THEN JSON_UNQUOTE(JSON_EXTRACT(ors_result_json, '$.rejected_because')) END
				AS ors_rejection_reason,
			source, linked_orders, last_verified_on
		FROM `tabShop Address Verification`
		WHERE {cond}
		ORDER BY modified DESC
		LIMIT %s OFFSET %s""",
		tuple(params) + (cint(limit), cint(offset)),
		as_dict=True,
	)

	return {
		"total": total,
		"rows": rows,
	}


@frappe.whitelist()
def get_verification_detail(name: str):
	"""Single verification record with full results + linked orders."""
	only_managers()
	ver = frappe.db.get_value(
		"Shop Address Verification", name,
		["*"],
		as_dict=True,
	)
	if not ver:
		frappe.throw(_("Verification record not found"))

	linked_orders = []
	if ver.linked_orders:
		order_names = [o.strip() for o in ver.linked_orders.split(",") if o.strip()]
		if order_names:
			linked_orders = frappe.db.sql(
				"""SELECT name, customer, grand_total, custom_fraud_verdict,
					custom_fraud_score, creation
				FROM `tabSales Order`
				WHERE name IN %s
				ORDER BY creation DESC""",
				(tuple(order_names),),
				as_dict=True,
			)

	return {
		"verification": ver,
		"linked_orders": linked_orders,
	}


@frappe.whitelist()
def reverify_address(name: str):
	"""Flag a record as queued (runs when Process Queue is pressed)."""
	only_managers()
	from shop.integrations.verification import reverify_address as _reverify
	return _reverify(name)


@frappe.whitelist()
def bulk_reverify(filters: dict = None, providers: str = "both"):
	"""Enqueue re-verification for all matching addresses.

	Filters are accepted for backwards compatibility but ignored —
	the queue processes every record that needs work."""
	only_managers()
	from shop.integrations.verification import start_queue_job
	job_id = start_queue_job(limit=None)
	return {"status": "queued", "job_id": job_id}


@frappe.whitelist()
def run_queue(limit: int = None):
	"""Start processing the verification queue in the background."""
	only_managers()
	from shop.integrations.verification import start_queue_job
	job_id = start_queue_job(limit=cint(limit) or None)
	return {"status": "queued", "job_id": job_id}


@frappe.whitelist()
def get_queue_status():
	"""Is a queue run active, and how many records still need work?"""
	only_managers()
	from shop.integrations.verification import queue_status
	return queue_status()


@frappe.whitelist()
def import_csv(csv_content: str):
	"""Import exported CSV. Upsert verification records. No background jobs."""
	only_managers()
	from shop.integrations.verification import import_verified_csv
	return import_verified_csv(csv_content)


@frappe.whitelist()
def export_csv(filters: dict = None):
	"""Enqueue CSV export background job."""
	only_managers()
	from shop.integrations.verification import export_verifications_csv
	job_id = export_verifications_csv(filters=filters)
	return {"status": "queued", "job_id": job_id}


@frappe.whitelist()
def get_export_status():
	"""Check if the most recent export exists, and name the file to fetch.

	No URL is returned: the file lives under private/files (it contains
	customer addresses) and a public /files/ link cannot resolve it.
	Use download_export() below.
	"""
	only_managers()
	from shop.integrations.verification import get_export_status as _status
	return _status()


@frappe.whitelist()
def download_export(filename: str = ""):
	"""Serve the verification export to a manager.

	Managers only, and only files this feature itself wrote: the name must
	match the export pattern, resolve inside private/files, and exist. Anything
	else is refused, so this cannot be turned into a general file read.
	"""
	only_managers()
	import os
	import re as _re

	pattern = _re.compile(r"^verifications_export_\d{8}_\d{6}\.csv$")
	basename = os.path.basename(str(filename or "").strip())
	if not pattern.match(basename):
		frappe.throw(_("Not a verification export file"), frappe.PermissionError)

	export_dir = os.path.realpath(frappe.get_site_path("private", "files"))
	path = os.path.realpath(os.path.join(export_dir, basename))
	if not path.startswith(export_dir + os.sep) or not os.path.isfile(path):
		frappe.throw(_("Export file not found"), frappe.DoesNotExistError)

	with open(path, "rb") as handle:
		frappe.response.filename = basename
		frappe.response.filecontent = handle.read()
	frappe.response.type = "download"


def _verdict(usable, degraded, total, down_count, min_samples=3):
	"""ok / warn / down / unknown / idle for one provider, and why.

	An API error is always "down", at any sample size: the provider answered and
	it was broken, which is actionable the moment it happens.

	A rejection rate is only "down" past 20%, and never at all below
	`min_samples` attempts. One unroutable address out of one is not a provider
	outage, and a dashboard that calls that "down" trains you to ignore it - some
	streets are genuinely unroutable, so a handful of rejections is normal and
	means nothing about the provider.

	Below the sample size the state is "unknown", not "warn": a provider at 100%
	usable should not carry an amber dot merely because there is one record, and
	an amber dot that does not mean anything is worse than no dot.
	"""
	if not total:
		return "idle", "No records in this window."
	if down_count:
		return (
			"down",
			f"{down_count} call{'s' if down_count != 1 else ''} failed outright "
			f"({100 * down_count // total}% of attempts). Check the API key and quota.",
		)
	if total < min_samples:
		return (
			"unknown",
			f"Only {total} attempt{'s' if total != 1 else ''} in this window, so there "
			"is no trend to read yet.",
		)
	if not degraded:
		return "ok", "Every record in this window produced a usable result."
	if usable * 5 < total:
		return (
			"down",
			f"Only {100 * usable // total}% of attempts produced a usable geocode. "
			"Treating most of this as provider failure, not customer risk.",
		)
	return (
		"warn",
		f"{degraded} of {total} attempts did not produce a usable geocode. "
		"Those records are scored on Google Maps alone and will be retried.",
	)


@frappe.whitelist()
def get_provider_health(days: int = 7):
	"""Are the geocoders actually working?

	This exists because that failure was completely silent. OpenRouteService
	returned a fallback match for every address, each stored as a Complete
	verification, and the only evidence anywhere was one customer's order score
	sitting 27 points too high. No screen said a provider was unwell.

	Scoped to records touched in the last `days` days so a provider that broke
	an hour ago reads as broken rather than being diluted by last month's
	successes. `modified` is used because the pipeline's final write bumps it.
	"""
	only_managers()
	window = max(1, min(cint(days) or 7, 365))
	since = add_days(nowdate(), -window)

	r = frappe.db.sql(
		"""SELECT
			COUNT(*) AS total,
			SUM(CASE WHEN ors_status = 'Complete' THEN 1 ELSE 0 END) AS ors_ok,
			SUM(CASE WHEN ors_status = 'Pending' THEN 1 ELSE 0 END) AS ors_pending,
			SUM(CASE WHEN ors_status = 'Failed'
				AND ors_result_json LIKE '%%rejected_because%%' THEN 1 ELSE 0 END) AS ors_rejected,
			SUM(CASE WHEN ors_status = 'Failed'
				AND (ors_result_json IS NULL OR ors_result_json NOT LIKE '%%rejected_because%%')
				THEN 1 ELSE 0 END) AS ors_errored,
			MAX(CASE WHEN ors_status = 'Complete' THEN ors_verified_on END) AS ors_last,
			SUM(CASE WHEN gms_status = 'Complete' THEN 1 ELSE 0 END) AS gms_ok,
			SUM(CASE WHEN gms_status = 'Pending' THEN 1 ELSE 0 END) AS gms_pending,
			SUM(CASE WHEN gms_status = 'Failed' THEN 1 ELSE 0 END) AS gms_failed,
			SUM(CASE WHEN gms_status = 'Disabled' THEN 1 ELSE 0 END) AS gms_disabled,
			MAX(CASE WHEN gms_status = 'Complete' THEN gms_verified_on END) AS gms_last,
			SUM(CASE WHEN ors_status IN ('Failed', 'Pending')
				OR gms_status IN ('Failed', 'Pending') THEN 1 ELSE 0 END) AS attention
		FROM `tabShop Address Verification`
		WHERE modified >= %s""",
		since,
		as_dict=True,
	)[0]

	total = cint(r.total)
	ors_attempts = cint(r.ors_ok) + cint(r.ors_rejected) + cint(r.ors_errored)
	ors_state, ors_note = _verdict(cint(r.ors_ok), cint(r.ors_rejected), ors_attempts, cint(r.ors_errored))
	gms_state, gms_note = _verdict(
		cint(r.gms_ok), cint(r.gms_failed), cint(r.gms_ok) + cint(r.gms_failed), cint(r.gms_failed)
	)

	return {
		"window_days": window,
		"since": since,
		"total_records": total,
		"needs_attention": cint(r.attention),
		"providers": [
			{
				"key": "ors",
				"name": "OpenRouteService",
				"state": ors_state,
				"note": ors_note,
				"usable": cint(r.ors_ok),
				"rejected": cint(r.ors_rejected),
				"failed": cint(r.ors_errored),
				"pending": cint(r.ors_pending),
				"attempts": ors_attempts,
				"usable_pct": round(100 * cint(r.ors_ok) / ors_attempts) if ors_attempts else None,
				"last_run": r.ors_last,
			},
			{
				"key": "gms",
				"name": "Google Maps",
				"state": gms_state,
				"note": gms_note,
				"usable": cint(r.gms_ok),
				"rejected": 0,
				"failed": cint(r.gms_failed),
				"pending": cint(r.gms_pending),
				"disabled": cint(r.gms_disabled),
				"attempts": cint(r.gms_ok) + cint(r.gms_failed),
				"usable_pct": (
					round(100 * cint(r.gms_ok) / (cint(r.gms_ok) + cint(r.gms_failed)))
					if (cint(r.gms_ok) + cint(r.gms_failed))
					else None
				),
				"last_run": r.gms_last,
			},
		],
	}


@frappe.whitelist()
def get_stats():
	"""Aggregated stats for the dashboard header."""
	only_managers()
	stats = frappe.db.sql(
		"""SELECT
			COUNT(*) as total,
			SUM(CASE WHEN ors_status='Complete' THEN 1 ELSE 0 END) as ors_complete,
			SUM(CASE WHEN ors_status='Pending' THEN 1 ELSE 0 END) as ors_pending,
			SUM(CASE WHEN ors_status='Failed' THEN 1 ELSE 0 END) as ors_failed,
			SUM(CASE WHEN gms_status='Complete' THEN 1 ELSE 0 END) as gms_complete,
			SUM(CASE WHEN gms_status='Pending' THEN 1 ELSE 0 END) as gms_pending,
			SUM(CASE WHEN gms_status='Failed' THEN 1 ELSE 0 END) as gms_failed,
			SUM(CASE WHEN gms_status='Disabled' THEN 1 ELSE 0 END) as gms_disabled
		FROM `tabShop Address Verification`""",
		as_dict=True,
	)
	cities = frappe.db.sql(
		"""SELECT city, COUNT(*) as cnt
		FROM `tabShop Address Verification`
		WHERE city IS NOT NULL AND city != ''
		GROUP BY city ORDER BY cnt DESC LIMIT 10""",
		as_dict=True,
	)
	return {
		"stats": stats[0] if stats else {},
		"top_cities": cities,
	}
