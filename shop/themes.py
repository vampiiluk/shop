import frappe
from frappe import _
from frappe.utils import now

HOME_ROUTE = "home"
LIVE_FOLDER = "Shop"  # legacy catch-all, retired by organize_template_folders()


@frappe.whitelist()
def list_themes() -> list[dict]:
	ensure_manager()
	from builder.template_sync import get_all_group_manifests

	settings = frappe.get_cached_doc("Shop Settings")
	themes = [
		{
			"group": group,
			"title": manifest.get("title") or group.title(),
			"description": manifest.get("description"),
			"preview": manifest.get("preview") or home_preview(group),
			"order": manifest.get("order", 0),
			"pages": manifest.get("pages", []),
			"active": group == settings.active_theme,
		}
		for group, manifest in get_all_group_manifests(app="shop").items()
	]
	return sorted(themes, key=lambda theme: theme["order"])


def home_preview(group: str) -> str | None:
	return frappe.db.get_value(
		"Builder Page",
		{"is_template": 1, "template_group": group, "route": HOME_ROUTE},
		"preview",
	)


def ensure_default_theme():
	"""Apply the lowest-order theme so a fresh install has a live storefront.

	Runs on every install/migrate but is a no-op once any theme is active.
	"""
	settings = frappe.get_cached_doc("Shop Settings")
	if settings.active_theme:
		return
	from builder.template_sync import get_all_group_manifests

	manifests = get_all_group_manifests(app="shop")
	if not manifests:
		return
	default_group = min(manifests, key=lambda group: manifests[group].get("order", 0))
	apply_theme(default_group)


@frappe.whitelist(methods=["POST"])
def apply_theme(group: str) -> None:
	ensure_manager()
	templates = template_pages(group)
	if not templates:
		frappe.throw(_("Theme {0} has no pages").format(group))
	settings = frappe.get_doc("Shop Settings")
	unpublish_active_theme(settings)
	tracked = {
		row.source_page: row
		for row in settings.theme_pages
		if row.template_group == group and frappe.db.exists("Builder Page", row.page)
	}
	for template_name in templates:
		if template_name in tracked:
			# Re-activation must also push the current template content: a clone
			# can predate a template regeneration, and its component overrides
			# would then reference block ids that no longer exist.
			republish(
				tracked[template_name].page, frappe.get_doc("Builder Page", template_name), group
			)
		else:
			clone_template(template_name, group, settings)
	settings.active_theme = group
	settings.save(ignore_permissions=True)
	set_home_page()
	clear_render_cache()


def clear_render_cache():
	"""Builder resolves a page's components through the cached Builder Component doc.

	A stale entry no longer matches the block ids the pages reference, so navbars,
	footers and drawers render as empty divs. clear-website-cache does not touch it.
	"""
	frappe.clear_cache()


def template_pages(group: str) -> list[str]:
	return frappe.get_all(
		"Builder Page", filters={"is_template": 1, "template_group": group}, pluck="name"
	)


def unpublish_active_theme(settings=None):
	settings = settings or frappe.get_doc("Shop Settings")
	for row in settings.theme_pages:
		if row.template_group != settings.active_theme:
			continue
		if not frappe.db.exists("Builder Page", row.page):
			continue
		page = frappe.get_doc("Builder Page", row.page)
		if page.published:
			page.published = 0
			page.save(ignore_permissions=True)


def republish(name: str, template: frappe.Document | None = None, group: str | None = None):
	page = frappe.get_doc("Builder Page", name)
	if template is not None:
		sync_clone(page, template)
	page.published = 1
	page.published_at = now()
	if group:
		page.project_folder = theme_folder(group)
	page.save(ignore_permissions=True)


def sync_clone(page: frappe.Document, template: frappe.Document) -> None:
	"""Push a template's content into an existing live clone in place."""
	page.blocks = template.blocks
	page.draft_blocks = template.blocks
	page.page_data_script = template.page_data_script
	page.body_html = template.body_html
	page.client_scripts = []
	for script in template.client_scripts:
		page.append("client_scripts", {"builder_script": script.builder_script})


def clone_template(template_name: str, group: str, settings):
	template = frappe.get_doc("Builder Page", template_name)
	clone = frappe.copy_doc(template)
	clone.page_name = live_page_name(template.page_name)
	clone.is_template = 0
	clone.template_group = None
	clone.is_standard = 0
	clone.app = None
	clone.route = template.route
	clone.draft_blocks = template.blocks
	clone.published = 1
	clone.published_at = now()
	clone.project_folder = theme_folder(group)
	clone.insert(ignore_permissions=True)
	settings.append(
		"theme_pages",
		{
			"template_group": group,
			"source_page": template_name,
			"page": clone.name,
			"route": clone.route,
		},
	)
	return clone.name


def live_page_name(page_name: str) -> str:
	name = f"{page_name}-live"
	if frappe.db.exists("Builder Page", name):
		name = f"{name}-{frappe.generate_hash(length=6)}"
	return name


def set_home_page():
	frappe.db.set_value("Builder Settings", None, "home_page", HOME_ROUTE)
	frappe.cache.delete_key("home_page")


def refresh_theme(group: str):
	"""Push updated template blocks into the live clones without unpublishing anything.

	reset + apply deletes the live pages first, which briefly serves shoppers a broken
	site. This updates each page in place and only clones pages that are new.
	"""
	ensure_manager()
	settings = frappe.get_doc("Shop Settings")
	tracked = {
		row.source_page: row
		for row in settings.theme_pages
		if row.template_group == group and frappe.db.exists("Builder Page", row.page)
	}
	for template_name in template_pages(group):
		template = frappe.get_doc("Builder Page", template_name)
		if template_name in tracked:
			page = frappe.get_doc("Builder Page", tracked[template_name].page)
			sync_clone(page, template)
			page.save(ignore_permissions=True)
		else:
			page = clone_template(template_name, group, settings)
			# `clone_template` publishes, but only apply_theme decides which
			# group is live — it unpublishes the outgoing group first. Refreshing
			# a group that is not active would otherwise insert a clone whose
			# `published_at` outranks the live theme's on the same route, and
			# find_page_with_path breaks that tie in its favour, serving a
			# different theme to every visitor than Settings says is active.
			if group != settings.active_theme:
				frappe.db.set_value(
					"Builder Page", page, "published", 0, update_modified=False
				)
	settings.save(ignore_permissions=True)
	set_home_page()
	clear_render_cache()


def reset_theme(group: str):
	"""Discard materialized pages for a group so the next apply re-clones from templates."""
	ensure_manager()
	settings = frappe.get_doc("Shop Settings")
	keep = []
	for row in settings.theme_pages:
		if row.template_group != group:
			keep.append(row)
		elif frappe.db.exists("Builder Page", row.page):
			frappe.delete_doc("Builder Page", row.page, ignore_permissions=True, force=True)
	settings.theme_pages = keep
	if settings.active_theme == group:
		settings.active_theme = None
	settings.save(ignore_permissions=True)


def ensure_folder(name: str) -> str:
	if not frappe.db.exists("Builder Project Folder", name):
		frappe.get_doc({"doctype": "Builder Project Folder", "folder_name": name}).insert(
			ignore_permissions=True
		)
	return name


def theme_folder(group: str) -> str:
	"""Folder for a theme: same title the organizer uses for its templates."""
	from builder.template_sync import get_group_manifest

	manifest = get_group_manifest(group, app="shop")
	return ensure_folder(manifest.get("title") or group.title())


def organize_template_folders():
	"""File each theme's templates and live clones under that theme's folder."""
	from builder.template_sync import get_all_group_manifests

	folders = {}
	for group, manifest in get_all_group_manifests(app="shop").items():
		folder = folders[group] = ensure_folder(manifest.get("title") or group.title())
		frappe.db.set_value(
			"Builder Page",
			{"is_template": 1, "template_group": group},
			"project_folder",
			folder,
			update_modified=False,
		)
	settings = frappe.get_cached_doc("Shop Settings")
	for group in {row.template_group for row in settings.theme_pages}:
		pages = [
			row.page
			for row in settings.theme_pages
			if row.template_group == group and frappe.db.exists("Builder Page", row.page)
		]
		if pages:
			frappe.db.set_value(
				"Builder Page",
				{"name": ["in", pages]},
				"project_folder",
				folders.get(group) or theme_folder(group),
				update_modified=False,
			)
	drop_empty_folder(LIVE_FOLDER)


def drop_empty_folder(name: str) -> None:
	"""Retire a folder once nothing pages at it (mirrors builder.api.delete_folder)."""
	if not frappe.db.exists("Builder Project Folder", name):
		return
	if frappe.db.exists("Builder Page", {"project_folder": name}):
		return
	frappe.db.delete("Builder Project Folder", {"folder_name": name})


def ensure_manager():
	frappe.only_for(("Shop Manager", "System Manager"))
