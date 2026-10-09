import os

import click

import frappe


def after_install():
	setup()


def after_migrate():
	setup()


def setup():
	create_shop_manager_role()
	apply_custom_fields()
	sync_templates()
	ensure_user_fonts()
	apply_default_theme()
	set_default_pdf_generator()
	sync_agent()
	enable_customer_signup()
	warn_if_server_scripts_disabled()
	download_gms_background()


def set_default_pdf_generator():
	"""Print through the chrome-headless-shell Frappe ships, not wkhtmltopdf.

	Frappe resolves a print format's engine as: the format's own setting, then
	the site default, then a hardcoded "wkhtmltopdf". There is no wkhtmltopdf
	binary on this platform - arm64 Linux has no official build - but the bench
	carries its own chrome-headless-shell under `chromium/`, which Frappe
	downloads for itself.

	So without a default set here, every print format that did not carry an
	explicit engine printed to a binary that does not exist and failed with
	"No wkhtmltopdf executable found". Setting the default fixes those formats
	and every format created later, which is what makes a fresh install print
	out of the box.

	Skipped when the site has deliberately chosen something else, so an admin
	who installs wkhtmltopdf and prefers it keeps their choice.
	"""
	if frappe.db.get_default("pdf_generator"):
		return
	if not _chrome_available():
		# Nothing to fall back to but wkhtmltopdf; saying so beats silently
		# setting a default that cannot run.
		click.secho(
			"No chrome-headless-shell found under the bench's chromium/ directory. "
			"Run: bench setup-chromium --yes (or install wkhtmltopdf).",
			fg="yellow",
		)
		return
	frappe.db.set_default("pdf_generator", "chrome")
	frappe.db.commit()


def _chrome_available() -> bool:
	import os

	bench = frappe.utils.get_bench_path()
	chromium = os.path.join(bench, "chromium")
	if not os.path.isdir(chromium):
		return False
	for root, _dirs, files in os.walk(chromium):
		if any(f in files for f in ("headless_shell", "chrome-headless-shell", "chrome")):
			return True
	return False


def apply_custom_fields():
	"""Frappe does not sync hooks-declared Custom Fields on its own - apply
	them explicitly (idempotent) so fresh installs and upgrades both get the
	full Address / Sales Order / Shop Settings field set."""
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	from shop.hooks import custom_fields

	create_custom_fields(custom_fields, ignore_validate=True, update=True)

	# Single doctypes have no table - their defaults must be seeded per-row,
	# otherwise settings like queue_schedule stay blank until first save.
	for dt, fields in custom_fields.items():
		try:
			if not frappe.get_meta(dt).issingle:
				continue
		except Exception:
			continue
		for f in fields:
			default = f.get("default")
			if default in (None, ""):
				continue
			if frappe.db.get_single_value(dt, f["fieldname"]) in (None, ""):
				# Write tabSingles directly - set_single_value() runs a full
				# document save whose Version diff can choke on fresh fields.
				frappe.db.sql(
					"""INSERT INTO `tabSingles` (doctype, field, value)
					VALUES (%s, %s, %s)
					ON DUPLICATE KEY UPDATE value = VALUES(value)""",
					(dt, f["fieldname"], str(default)),
				)
	frappe.db.commit()


def download_gms_background():
	"""Auto-download GMS binary in background if not already installed."""
	try:
		from shop.integrations.gms import get_gms_binary
		if get_gms_binary():
			return
		# Download in background via frappe.enqueue
		frappe.enqueue(
			"shop.integrations.gms.download_gms",
			queue="short",
			timeout=60,
			after_commit=True,
		)
	except Exception:
		pass


def enable_customer_signup():
	"""Shoppers need accounts to track orders, so the store cannot ship with signup off."""
	if frappe.db.get_single_value("Website Settings", "disable_signup"):
		frappe.db.set_single_value("Website Settings", "disable_signup", 0)


def sync_agent():
	from shop.agent.setup import sync

	sync()


def create_shop_manager_role():
	if frappe.db.exists("Role", "Shop Manager"):
		return
	frappe.get_doc({"doctype": "Role", "role_name": "Shop Manager", "desk_access": 1}).insert(
		ignore_permissions=True
	)


def sync_templates():
	if not os.path.exists(frappe.get_app_path("shop", "builder_templates")):
		return
	from builder.template_sync import sync_builder_templates

	from shop.themes import organize_template_folders

	sync_builder_templates(app="shop", publish=False)
	organize_template_folders()


def ensure_user_fonts():
	"""Seed the User Font records that take storefront pages off Google Fonts.

	The woff2 files ship with this app, but the records that make Builder's
	stock set_custom_font() swap the Google URLs for local ones are data.
	Creates them on install/migrate; existing records are never touched.
	Without the files a record would 404 and break text rendering worse than
	the Google CDN does, so a missing file keeps the stock Google fallback."""
	font_files = {
		"Space Grotesk": "space-grotesk.woff2",
		"DM Mono": "dm-mono.woff2",
	}
	fonts_dir = os.path.join(frappe.get_app_path("shop"), "public", "fonts")
	missing = [f for f in font_files.values() if not os.path.exists(os.path.join(fonts_dir, f))]
	if missing:
		click.secho(
			f"Storefront font files missing ({', '.join(missing)}) - pages keep using Google Fonts.",
			fg="yellow",
		)
		return

	created = False
	for font_name, filename in font_files.items():
		if frappe.db.exists("User Font", font_name):
			continue
		frappe.get_doc(
			{
				"doctype": "User Font",
				"font_name": font_name,
				"font_file": f"/assets/shop/fonts/{filename}",
			}
		).insert(ignore_permissions=True)
		created = True
	if created:
		frappe.db.commit()


def apply_default_theme():
	from shop.themes import ensure_default_theme

	ensure_default_theme()


def warn_if_server_scripts_disabled():
	from frappe.utils.safe_exec import is_safe_exec_enabled

	if not is_safe_exec_enabled():
		click.secho(
			"Shop storefront pages require server scripts. "
			"Run: bench set-config --global server_script_enabled 1",
			fg="yellow",
		)


def before_tests():
	frappe.clear_cache()
	from shop.demo import setup as setup_demo_data

	setup_demo_data()
