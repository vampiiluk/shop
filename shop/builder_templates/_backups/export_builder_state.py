import frappe, json, pathlib, datetime

frappe.init(site="erp.sananahmad.dpdns.org", sites_path="/home/frappe/pilot/benches/erp/sites")
frappe.connect()
frappe.set_user("Administrator")
frappe.flags.in_test = False

stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
BACKUP_DIR = pathlib.Path("/home/frappe/builder-backups")
BACKUP_DIR.mkdir(parents=True, exist_ok=True)
out = BACKUP_DIR / f"builder-backup-{stamp}.json"

DOCTYPE_FIELDS = {
	"Builder Page": ["name", "page_name", "page_title", "route", "dynamic_route",
					 "published", "is_template", "template_group", "app",
					 "blocks", "draft_blocks", "page_data_script", "head_html",
					 "body_html", "meta_description", "authenticated_access",
					 "disable_indexing"],
	"Builder Component": ["name", "component_name", "component_id", "block",
						  "for_web_page", "component_data_script"],
	"Builder Variable": ["name", "variable_name", "group", "type", "value", "dark_value"],
	"Builder Client Script": ["name", "script_type", "script", "public_url"],
}

dump = {"taken_at": stamp, "site": "erp.sananahmad.dpdns.org", "doctypes": {}}

for dt, fields in DOCTYPE_FIELDS.items():
	try:
		rows = frappe.get_all(dt, fields=fields)
	except Exception as e:
		dump["doctypes"][dt] = {"error": f"{type(e).__name__}: {e}"}
		continue
	dump["doctypes"][dt] = rows
	print(f"  {dt:<24} {len(rows)} row(s)")

out.write_text(json.dumps(dump, indent=1, default=str))
print(f"\n  wrote {out}  ({out.stat().st_size // 1024} KB)")

# A restorable fixture too, in case the JSON is ever unreadable.
fixtures = []
for dt, fields in DOCTYPE_FIELDS.items():
	rows = frappe.get_all(dt, fields=fields)
	for r in rows:
		fixtures.append({**{k: v for k, v in r.items()}, "doctype": dt})
fx = BACKUP_DIR / f"builder-backup-fixtures-{stamp}.json"
fx.write_text(json.dumps(fixtures, indent=1, default=str))
print(f"  wrote {fx}  ({fx.stat().st_size // 1024} KB, {len(fixtures)} fixture rows)")

# and a copy inside the repo, so it travels with the code
repo = pathlib.Path("/home/frappe/pilot/benches/erp/apps/shop/builder_templates/_backups")
repo.mkdir(parents=True, exist_ok=True)
dest = repo / f"builder_state_{stamp}.json"
dest.write_text(out.read_text())
print(f"  wrote {dest}")
