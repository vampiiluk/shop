"""Verification dashboard API endpoints."""

import frappe
from frappe import _
from frappe.utils import cint

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

	total = frappe.db.sql(
		f"SELECT COUNT(*) FROM `tabShop Address Verification` WHERE {cond}",
		tuple(params),
	)[0][0]

	rows = frappe.db.sql(
		f"""SELECT name, address_hash, address_line1, city, landmark, country, pincode,
			latitude, longitude, status, ors_status, gms_status, gms_result_count,
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
	"""Check if most recent export file exists, return URL."""
	only_managers()
	from shop.integrations.verification import get_export_status as _status
	return _status()


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
