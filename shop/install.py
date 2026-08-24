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
	apply_default_theme()
	sync_agent()
	enable_customer_signup()
	warn_if_server_scripts_disabled()
	download_gms_background()


def apply_custom_fields():
	"""Frappe does not sync hooks-declared Custom Fields on its own - apply
	them explicitly (idempotent) so fresh installs and upgrades both get the
	full Address / Sales Order / Shop Settings field set."""
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	from shop.hooks import custom_fields

	create_custom_fields(custom_fields, ignore_validate=True, update=True)


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
