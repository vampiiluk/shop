import frappe

AGENT_TITLE = "Shop Assistant"
TOOL_MODULE = "shop.agent.tools"
MAX_ITERATIONS = 25

INSTRUCTIONS = (
	"You run an online store for its owner. You can inspect and change the catalogue, "
	"stock, orders, customers, discounts and store settings through your tools, and the "
	"storefront itself is edited visually in Builder.\n\n"
	"HOW TO WORK: read before you write. Check the current state with a listing or details "
	"tool before changing anything, so you can tell the owner what will change. Say in one "
	"short sentence what you are about to do before each tool call. Tools that change the "
	"store ask the owner to confirm, so propose the exact change rather than asking open "
	"questions first. If a request is ambiguous in a way that matters, for example which of "
	"two similarly named products, ask one short question and stop.\n\n"
	"WHAT GOOD LOOKS LIKE: when the owner asks to set up a store, use setup_progress to see "
	"what is missing and work through it. When adding products, write a short honest "
	"description and set a sensible price; never invent stock you were not told about. When "
	"asked how the store is doing, lead with the number that answers the question, then the "
	"one detail that explains it.\n\n"
	"LIMITS: you cannot take payments, contact customers, or edit page design. For design "
	"changes, point the owner at the storefront pages you can list. Never claim an action "
	"succeeded unless the tool returned successfully. Report money and dates exactly as the "
	"tools return them."
)


def sync():
	"""Register the shop's tools and assistant with Flow. Safe to run repeatedly."""
	if "flow" not in frappe.get_installed_apps():
		return
	slugs = sync_tools()
	sync_agent(slugs)


def sync_tools() -> list[str]:
	from flow import Tool

	import shop.agent.tools as tools_module

	slugs = []
	for name in dir(tools_module):
		candidate = getattr(tools_module, name)
		if not isinstance(candidate, Tool):
			continue
		slugs.append(candidate.name)
		upsert_tool(candidate)
	return slugs


def upsert_tool(tool) -> None:
	import_path = f"{TOOL_MODULE}.{tool.name}"
	values = {
		"import_path": import_path,
		"description": tool.description,
		"requires_confirmation": int(tool.requires_confirmation),
		"is_system_generated": 1,
	}
	if frappe.db.exists("Flow Tool", tool.name):
		frappe.db.set_value("Flow Tool", tool.name, values)
		return
	frappe.get_doc(
		{
			"doctype": "Flow Tool",
			"slug": tool.name,
			"title": tool.name.replace("_", " ").capitalize(),
			"type": "Imported",
			**values,
		}
	).insert(ignore_permissions=True)


def chat_model() -> str | None:
	"""First enabled Flow Model that can actually chat.

	Skips embedding models and models without an API key - either would
	leave the assistant unusable. Falls back to any enabled model.
	"""
	rows = frappe.get_all(
		"Flow Model",
		filters={"enabled": 1},
		fields=["name", "api_key", "model_id"],
		order_by="creation asc",
	)
	usable = None
	for row in rows:
		model_id = (row.model_id or "").lower()
		if "embed" in model_id:
			continue
		usable = usable or row.name
		if row.api_key:
			return row.name
	return usable


def sync_agent(slugs: list[str]) -> None:
	model = chat_model()
	if not frappe.db.exists("Flow Agent", AGENT_TITLE):
		if not model:
			return
		frappe.get_doc(
			{
				"doctype": "Flow Agent",
				"title": AGENT_TITLE,
				"model": model,
				"instructions": INSTRUCTIONS,
				"max_iterations": MAX_ITERATIONS,
				"tools": [{"tool": slug} for slug in slugs],
				"enabled": 1,
				"is_system_generated": 1,
			}
		).insert(ignore_permissions=True)
		return
	agent = frappe.get_doc("Flow Agent", AGENT_TITLE)
	if not agent.is_system_generated:
		return
	agent.instructions = INSTRUCTIONS
	agent.model = agent.model or model
	existing = {row.tool for row in agent.tools}
	for slug in slugs:
		if slug not in existing:
			agent.append("tools", {"tool": slug})
	agent.save(ignore_permissions=True)


@frappe.whitelist()
def get_agent_status() -> dict:
	"""Whether the assistant is ready, and why not when it is not."""
	from shop.api import only_managers

	only_managers()
	if "flow" not in frappe.get_installed_apps():
		return {"ready": False, "reason": "not_installed"}
	if not frappe.db.exists("Flow Agent", AGENT_TITLE):
		# A model is often configured after the last migrate. Build the
		# agent on demand so the assistant comes online without waiting.
		if chat_model():
			try:
				sync()
			except Exception:
				frappe.log_error(title="Shop assistant sync failed")
	agent = frappe.db.get_value("Flow Agent", AGENT_TITLE, ["enabled", "model"], as_dict=True)
	if not agent or not agent.model:
		return {"ready": False, "reason": "no_model"}
	return {
		"ready": bool(agent.enabled),
		"agent": AGENT_TITLE,
		"model": agent.model,
		"tools": frappe.db.count("Flow Agent Tool", {"parent": AGENT_TITLE}),
	}
