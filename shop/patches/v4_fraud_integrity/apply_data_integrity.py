"""Make one address mean one verification row, and one city mean one stats row.

Runs post_model_sync. Nothing here changes what the engine scores; it removes
two ways for the data to disagree with itself.

1. `Shop Address Verification.address_hash` becomes unique. The hash is derived
   from the address text, so two rows with the same hash are the same address
   twice: the fraud KPIs counted their orders twice, and `evaluate_risk` read
   whichever copy's risk score it happened to get. Existing duplicates are
   merged into the newest row (linked orders/phones/fingerprints carried over)
   before the index is created.

2. `Shop City Stats.city` is normalised (case, padding, inner spacing collapsed)
   and made unique, so "Rahimyar Yar Khan" and "Rahim Yar Khan" can no longer be
   two rows with two RTO rates, half of which no lookup ever finds. Existing
   rows are merged by summing the counters and keeping the highest rate.
"""

import frappe

from shop.integrations.fraud import normalize_city

HASH_TABLE = "`tabShop Address Verification`"
CITY_TABLE = "`tabShop City Stats`"


def _merge_duplicate_hashes() -> int:
	"""Fold duplicate hashes into the newest row of each group."""
	groups = frappe.db.sql(
		f"""
		SELECT address_hash, COUNT(*) AS copies
		FROM {HASH_TABLE}
		WHERE address_hash IS NOT NULL AND address_hash != ''
		GROUP BY address_hash
		HAVING COUNT(*) > 1
		""",
		as_dict=True,
	)
	merged = 0
	for group in groups:
		rows = frappe.db.sql(
			f"""
			SELECT name, linked_orders, linked_phones, linked_fingerprints
			FROM {HASH_TABLE}
			WHERE address_hash = %(hash)s
			ORDER BY creation DESC
			""",
			{"hash": group.address_hash},
			as_dict=True,
		)
		if len(rows) < 2:
			continue
		keep, duplicates = rows[0], rows[1:]
		frappe.logger("fraud").info(
			"merging %s duplicate verification rows into %s (hash %s)",
			len(duplicates),
			keep.name,
			group.address_hash,
		)
		for field in ("linked_orders", "linked_phones", "linked_fingerprints"):
			values: list[str] = []
			for row in [keep, *duplicates]:
				values.extend([v.strip() for v in (row.get(field) or "").split(",") if v.strip()])
			frappe.db.set_value(
				"Shop Address Verification", keep.name, {field: ", ".join(dict.fromkeys(values))}
			)
		frappe.db.sql(
			f"DELETE FROM {HASH_TABLE} WHERE name in %(names)s",
			{"names": tuple(row.name for row in duplicates)},
		)
		merged += len(duplicates)
	frappe.db.commit()
	return merged


def _normalise_city_rows() -> int:
	"""Merge city-stats rows that differ only in spelling."""
	rows = frappe.db.sql(
		f"SELECT name, city, creation, orders_30d, failed_30d, rto_rate FROM {CITY_TABLE}",
		as_dict=True,
	)
	groups: dict[str, list] = {}
	for row in rows:
		groups.setdefault(normalize_city(row.city), []).append(row)
	merged = 0
	for key, group in groups.items():
		group.sort(key=lambda r: r.creation or "", reverse=True)
		if len(group) > 1:
			keep, duplicates = group[0], group[1:]
			frappe.db.set_value(
				"Shop City Stats",
				keep.name,
				{
					"city": key,
					"orders_30d": sum(int(r.orders_30d or 0) for r in group),
					"failed_30d": sum(int(r.failed_30d or 0) for r in group),
					"rto_rate": max(float(r.rto_rate or 0) for r in group),
				},
			)
			frappe.db.sql(
				f"DELETE FROM {CITY_TABLE} WHERE name in %(names)s",
				{"names": tuple(r.name for r in duplicates)},
			)
			merged += len(duplicates)
		elif key and key != group[0].city:
			# Same single row, new spelling: rewrite the key in place.
			frappe.db.set_value("Shop City Stats", group[0].name, {"city": key})
	frappe.db.commit()
	return merged


def _add_unique_indexes() -> None:
	for table, column, index_name in (
		(HASH_TABLE, "address_hash", "shop_address_verification_address_hash_unique"),
		(CITY_TABLE, "city", "shop_city_stats_city_unique"),
	):
		existing = frappe.db.sql(
			"SELECT INDEX_NAME FROM `information_schema`.STATISTICS "
			"WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s",
			(table.replace("`", ""), column),
			pluck="INDEX_NAME",
		)
		if existing:
			continue
		try:
			frappe.db.sql(f"CREATE UNIQUE INDEX `{index_name}` ON {table} (`{column}`)")
		except Exception as exc:  # duplicates may survive on a re-run
			frappe.logger("fraud").warning(
				"could not add %s on %s(%s): %s", index_name, table, column, exc
			)
	frappe.db.commit()


def execute():
	merged_hashes = _merge_duplicate_hashes()
	merged_cities = _normalise_city_rows()
	_add_unique_indexes()
	frappe.logger("fraud").info(
		"fraud data-integrity patch: %s duplicate verification rows merged, %s duplicate city rows merged",
		merged_hashes,
		merged_cities,
	)
