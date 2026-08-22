"""CSV import for the Shop Landmark table (google-maps-scraper output)."""

import csv
import hashlib
import io

import frappe
from frappe import _
from frappe.utils import cint, flt

from shop.api import only_managers
from shop.integrations.geocoding import norm_text

EXPECTED_COLUMNS = [
	"input_id",
	"title",
	"category",
	"address",
	"latitude",
	"longitude",
	"phone",
	"place_id",
]


def _dedupe_key(title_norm: str, lat: float, lng: float, place_id: str) -> str:
	if place_id:
		return "pid:" + place_id
	raw = f"{title_norm}|{round(lat, 4)}|{round(lng, 4)}"
	return "geo:" + hashlib.md5(raw.encode()).hexdigest()


@frappe.whitelist(methods=["POST"])
def import_landmarks(csv_content: str = "", source: str = "google") -> dict:
	"""Import a landmarks CSV (slim google-maps-scraper output).

	Expected columns: input_id ('city|category'), title, category,
	address, latitude, longitude, phone, place_id.
	"""
	from shop.api import only_managers

	only_managers()

	if not csv_content or not csv_content.strip():
		frappe.throw(_("Empty CSV content"))

	reader = csv.DictReader(io.StringIO(csv_content))
	missing = [c for c in ("title", "latitude", "longitude") if c not in (reader.fieldnames or [])]
	if missing:
		frappe.throw(_("Missing required columns: {0}").format(", ".join(missing)))

	inserted = updated = skipped = 0
	errors = []
	batch = []

	for idx, row in enumerate(reader, start=2):  # header is line 1
		title = (row.get("title") or "").strip()
		try:
			lat = flt(row.get("latitude"))
			lng = flt(row.get("longitude"))
		except Exception:
			lat = lng = 0

		if not title or not lat or not lng:
			skipped += 1
			continue

		input_id = (row.get("input_id") or "").strip()
		city, id_category = "", ""
		if "|" in input_id:
			id_city, _, id_category = input_id.partition("|")
			city = id_city.strip().replace("-", " ").title()
		category = (row.get("category") or id_category).strip()

		name_norm = norm_text(title)
		key = _dedupe_key(name_norm, lat, lng, (row.get("place_id") or "").strip())
		values = {
			"landmark_name": title[:140],
			"normalized_name": name_norm[:140],
			"category": category[:140],
			"city": city[:140],
			"latitude": lat,
			"longitude": lng,
			"phone": (row.get("phone") or "").strip(),
			"place_id": (row.get("place_id") or "").strip(),
			"source": source,
			"dedupe_key": key,
		}

		existing = frappe.db.get_value("Shop Landmark", {"dedupe_key": key}, "name")
		if existing:
			frappe.db.set_value("Shop Landmark", existing, values, update_modified=False)
			updated += 1
		else:
			doc = frappe.new_doc("Shop Landmark")
			doc.update(values)
			batch.append(doc)
			inserted += 1

		if len(batch) >= 500:
			for doc in batch:
				doc.insert(ignore_permissions=True)
			batch.clear()

	for doc in batch:
		doc.insert(ignore_permissions=True)

	frappe.db.commit()
	return {
		"inserted": inserted,
		"updated": updated,
		"skipped": skipped,
		"errors": errors[:20],
		"total_landmarks": cint(frappe.db.count("Shop Landmark")),
	}


@frappe.whitelist()
def landmark_stats() -> dict:
	"""Counts for the imports page."""
	from shop.api import only_managers

	only_managers()
	rows = frappe.get_all(
		"Shop Landmark",
		fields=["city", "category", {"COUNT": "name", "as": "total"}],
		group_by="city, category",
		order_by="city asc",
		limit=0,
	)
	by_city = {}
	for row in rows:
		entry = by_city.setdefault(row.city or "Unknown", {"city": row.city or "Unknown", "total": 0})
		entry["total"] += row.total

	return {
		"total": frappe.db.count("Shop Landmark"),
		"cities": sorted(by_city.values(), key=lambda x: -x["total"]),
		"by_category": [
			{"category": r.category or "Unknown", "total": r.total}
			for r in frappe.get_all(
				"Shop Landmark",
				fields=["category", {"COUNT": "name", "as": "total"}],
				group_by="category",
				order_by="total desc",
				limit=0,
			)
		],
	}
