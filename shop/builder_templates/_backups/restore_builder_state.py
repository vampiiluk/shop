#!/usr/bin/env python
"""Restore Builder state (pages, components, variables, client scripts) from a backup.

Usage:
    bench --site <site> execute builder_templates._backups.restore_builder_state --args "<path-to-json>"

or

    ../env/bin/python restore_builder_state.py /home/frappe/builder-backups/builder-backup-<stamp>.json

The backup is a flat dict of doctype -> rows, as written by export_builder_state.py.
Rows are upserted by `name`, then the route caches are dropped, because a Builder
Page whose blocks changed will keep serving the old markup until
`get_web_pages_with_dynamic_routes` / `find_page_with_path` are cleared.

Writes are not committed until the very end, so a failure part-way leaves the
database untouched.
"""

import json
import sys

import frappe

DOCTYPES = ("Builder Page", "Builder Component", "Builder Variable", "Builder Client Script")


def restore(path, dry_run=False):
	with open(path) as f:
		blob = json.load(f)

	dump = blob["doctypes"] if "doctypes" in blob else {}
	if not dump:
		# the fixture form: a flat list of rows, each tagged with its doctype
		rows = blob if isinstance(blob, list) else []
		dump = {}
		for row in rows:
			dump.setdefault(row["doctype"], []).append(row)

	print(f"  restoring from {path}")
	for dt in DOCTYPES:
		rows = dump.get(dt) or []
		if not rows:
			continue
		existing = {r.name for r in frappe.get_all(dt, fields=["name"])}
		added = updated = 0
		for row in rows:
			name = row.get("name")
			if not name:
				continue
			payload = {k: v for k, v in row.items() if k not in ("name", "doctype")}
			if dry_run:
				added += name not in existing
				updated += name in existing
				continue
			if frappe.db.exists(dt, name):
				frappe.db.set_value(dt, name, payload, update_modified=False)
				updated += 1
			else:
				payload["doctype"] = dt
				doc = frappe.new_doc(dt)
				doc.update(payload)
				doc.insert(ignore_if_duplicate=True, ignore_permissions=True)
				added += 1
		verb = "would write" if dry_run else "wrote"
		print(f"    {dt:<24} {len(rows)} row(s) -> {added} new, {updated} existing ({verb})")

	if dry_run:
		frappe.db.rollback()
		print("  dry run: nothing committed")
		return

	for dt in DOCTYPES:
		frappe.clear_document_cache(dt)
	for page in frappe.get_all("Builder Page", filters={"published": 1}, fields=["name"]):
		frappe.get_doc("Builder Page", page.name).clear_route_cache()
	for route in frappe.get_all("Builder Page", filters={"published": 1}, fields=["route"]):
		frappe.website.utils.clear_cache(route.route)

	frappe.db.commit()
	print("  committed; route caches cleared")


if __name__ == "__main__":
	frappe.init(site="erp.sananahmad.dpdns.org", sites_path="/home/frappe/pilot/benches/erp/sites")
	frappe.connect()
	restore(sys.argv[1], dry_run="--dry-run" in sys.argv)