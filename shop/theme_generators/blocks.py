"""Helpers for generating Builder Page block trees programmatically."""

import frappe


def block(
	element: str = "div",
	styles: dict | None = None,
	mobile: dict | None = None,
	tablet: dict | None = None,
	children: list | None = None,
	name: str | None = None,
	text: str | None = None,
	attrs: dict | None = None,
	classes: list | None = None,
	**extra,
) -> dict:
	node = {
		"blockId": frappe.generate_hash(length=10),
		"element": element,
		"attributes": attrs or {},
		"customAttributes": {},
		"classes": classes or [],
		"baseStyles": styles or {},
		"mobileStyles": mobile or {},
		"tabletStyles": tablet or {},
		"children": children or [],
	}
	if name:
		node["blockName"] = name
	if text is not None:
		node["innerHTML"] = text
	node.update(extra)
	return node


def root(styles: dict, children: list) -> dict:
	node = block("div", styles=styles, children=children, name="Root")
	node["originalElement"] = "body"
	return node


def dv(key: str, prop: str, kind: str = "key") -> dict:
	return {"comesFrom": "dataScript", "key": key, "property": prop, "type": kind}


# WhatsApp brand green, shared by the storefront's WhatsApp CTAs.
WHATSAPP_GREEN = "#25D366"

# Official WhatsApp glyph (simple-icons, 24x24 viewBox).
WHATSAPP_PATH = (
	"M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164"
	"-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297"
	"-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075"
	"-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792"
	".372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306"
	" 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173"
	"-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982"
	".998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988"
	" 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05"
	" 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683"
	" 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413Z"
)


def whatsapp_icon(size: int = 15) -> dict:
	"""WhatsApp glyph for the "Buy on WhatsApp" button.

	Built as child blocks rather than an innerHTML string: the renderer parses
	innerHTML with BeautifulSoup's html.parser, which lowercases attribute
	names and would mangle the camelCase ``viewBox``. Filled with
	``currentColor`` so it always matches the button's text colour.
	"""
	return block(
		"svg",
		attrs={
			"aria-hidden": "true",
			"fill": "currentColor",
			"height": str(size),
			"viewBox": "0 0 24 24",
			"width": str(size),
			"xmlns": "http://www.w3.org/2000/svg",
		},
		children=[block("path", attrs={"d": WHATSAPP_PATH})],
	)


def repeater(key: str, child: dict, styles: dict, element: str = "div", **kwargs) -> dict:
	return block(
		element,
		styles=styles,
		children=[child],
		isRepeaterBlock=True,
		dataKey={"key": key, "comesFrom": "dataScript"},
		**kwargs,
	)


def upsert_component(component_id: str, component_name: str, block: dict) -> str:
	existing = frappe.db.exists("Builder Component", component_id)
	doc = frappe.get_doc("Builder Component", component_id) if existing else frappe.new_doc("Builder Component")
	doc.component_id = component_id
	doc.component_name = component_name
	doc.block = frappe.as_json(block)
	doc.save(ignore_permissions=True) if existing else doc.insert(ignore_permissions=True)
	return doc.name


def component_ref(component_id: str) -> dict:
	"""Block that renders a registered Builder Component, mirroring its children
	the way the editor does so overrides can attach per child."""
	source = frappe.parse_json(frappe.get_doc("Builder Component", component_id).block or "{}")
	return {
		"blockId": frappe.generate_hash(length=10),
		"extendedFromComponent": component_id,
		"children": [component_child_ref(child, component_id) for child in source.get("children") or []],
	}


def component_child_ref(source: dict, component_id: str) -> dict:
	return {
		"blockId": frappe.generate_hash(length=10),
		"isChildOfComponent": component_id,
		"referenceBlockId": source.get("blockId"),
		"children": [component_child_ref(child, component_id) for child in source.get("children") or []],
	}


def upsert_page(
	group: str,
	page_name: str,
	page_title: str,
	route: str,
	blocks: list,
	data_script: str,
	client_scripts: list[str] | None = None,
	authenticated_access: bool = False,
	meta_description: str | None = None,
):
	existing = frappe.db.exists(
		"Builder Page", {"template_group": group, "is_template": 1, "route": route}
	)
	page = frappe.get_doc("Builder Page", existing) if existing else frappe.new_doc("Builder Page")
	page.update(
		{
			"page_name": page_name,
			"page_title": page_title,
			"route": route,
			"is_template": 1,
			"template_group": group,
			"published": 0,
			"blocks": frappe.as_json(blocks),
			"draft_blocks": None,
			"page_data_script": data_script,
			"body_html": '<script src="/assets/shop/js/storefront.js?v=20" defer></script>',
			"authenticated_access": 1 if authenticated_access else 0,
			"meta_description": meta_description,
			"client_scripts": [],
		}
	)
	for script in client_scripts or []:
		page.append("client_scripts", {"builder_script": script})
	page.save(ignore_permissions=True) if existing else page.insert(ignore_permissions=True)
	return page


def upsert_variables(group: str, palette: dict[str, tuple[str, str | None]]) -> dict[str, str]:
	"""palette: {variable_name: (value, dark_value)} -> {variable_name: css var() reference}"""
	refs = {}
	for variable_name, (value, dark_value) in palette.items():
		name = frappe.db.exists("Builder Variable", {"variable_name": variable_name, "group": group})
		if name:
			doc = frappe.get_doc("Builder Variable", name)
		else:
			doc = frappe.new_doc("Builder Variable")
			doc.variable_name = variable_name
		doc.type = "Color"
		doc.value = value
		doc.dark_value = dark_value
		doc.group = group
		doc.save(ignore_permissions=True) if name else doc.insert(ignore_permissions=True)
		refs[variable_name] = f"var(--{doc.name}, {value})"
	return refs


def upsert_client_script(name: str, script_type: str, script: str) -> str:
	existing = frappe.db.exists("Builder Client Script", {"name": name})
	doc = frappe.get_doc("Builder Client Script", existing) if existing else frappe.new_doc("Builder Client Script")
	doc.update({"script_type": script_type, "script": script})
	if not existing:
		doc.name = name
	doc.save(ignore_permissions=True) if existing else doc.insert(ignore_permissions=True, set_name=name)
	return doc.name
