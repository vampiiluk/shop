import frappe
from frappe.utils import cint, flt

from shop.api import only_managers
from shop.storefront import pricing


@frappe.whitelist()
def get_customers(search: str | None = None, start: int = 0, limit: int = 20) -> dict:
	only_managers()
	filters = {"disabled": 0}
	or_filters = None
	if search:
		term = f"%{search.strip()}%"
		or_filters = [["customer_name", "like", term], ["name", "like", term]]
	customers = frappe.get_all(
		"Customer",
		filters=filters,
		or_filters=or_filters,
		fields=["name", "customer_name", "creation"],
		order_by="creation desc",
		start=cint(start),
		limit=min(cint(limit) or 20, 100),
	)
	totals = order_totals([customer.name for customer in customers])
	emails = contact_emails([customer.name for customer in customers])
	for customer in customers:
		summary = totals.get(customer.name, {"orders": 0, "spent": 0.0, "last": None})
		customer["orders"] = summary["orders"]
		customer["formatted_spent"] = pricing.format_amount(summary["spent"])
		customer["last_order"] = summary["last"]
		customer["email"] = emails.get(customer.name)
		customer["joined"] = str(customer.creation)[:10]
		del customer["creation"]
	return {"customers": customers, "total": frappe.db.count("Customer", filters=filters)}


def order_totals(names: list[str]) -> dict:
	if not names:
		return {}
	rows = frappe.get_all(
		"Sales Order",
		filters={"customer": ["in", names], "docstatus": 1},
		fields=["customer", "grand_total", "transaction_date"],
		order_by="transaction_date desc",
	)
	summary = {}
	for row in rows:
		entry = summary.setdefault(row.customer, {"orders": 0, "spent": 0.0, "last": None})
		entry["orders"] += 1
		entry["spent"] += flt(row.grand_total)
		entry["last"] = entry["last"] or str(row.transaction_date)
	return summary


def contact_emails(names: list[str]) -> dict:
	if not names:
		return {}
	links = frappe.get_all(
		"Dynamic Link",
		filters={"parenttype": "Contact", "link_doctype": "Customer", "link_name": ["in", names]},
		fields=["parent", "link_name"],
	)
	if not links:
		return {}
	emails = frappe.get_all(
		"Contact Email",
		filters={"parent": ["in", [link.parent for link in links]]},
		fields=["parent", "email_id"],
	)
	by_contact = {row.parent: row.email_id for row in emails}
	return {link.link_name: by_contact.get(link.parent) for link in links if by_contact.get(link.parent)}


def all_contact_emails(names: list[str]) -> dict[str, list[str]]:
	"""All emails for each customer (not just primary)."""
	if not names:
		return {}
	links = frappe.get_all(
		"Dynamic Link",
		filters={"parenttype": "Contact", "link_doctype": "Customer", "link_name": ["in", names]},
		fields=["parent", "link_name"],
	)
	if not links:
		return {}
	contact_parents = list({link.parent for link in links})
	emails = frappe.get_all(
		"Contact Email",
		filters={"parent": ["in", contact_parents]},
		fields=["parent", "email_id"],
	)
	by_contact: dict[str, list[str]] = {}
	for row in emails:
		by_contact.setdefault(row.parent, []).append(row.email_id.strip().lower())
	result: dict[str, list[str]] = {}
	for link in links:
		for em in by_contact.get(link.parent, []):
			result.setdefault(link.link_name, [])
			if em not in result[link.link_name]:
				result[link.link_name].append(em)
	return result


@frappe.whitelist()
def get_customer(name: str) -> dict:
	only_managers()
	customer = frappe.get_doc("Customer", name)
	orders = frappe.get_all(
		"Sales Order",
		filters={"customer": name, "docstatus": ["<", 2]},
		fields=["name", "transaction_date", "status", "grand_total"],
		order_by="creation desc",
	)
	for order in orders:
		order["formatted_total"] = pricing.format_amount(order.grand_total)
	emails_map = all_contact_emails([name])
	primary_email = emails_map.get(name, [None])[0] if emails_map.get(name) else None
	return {
		"name": customer.name,
		"customer_name": customer.customer_name,
		"email": primary_email,
		"all_emails": emails_map.get(name, []),
		"joined": str(customer.creation)[:10],
		"orders": orders,
		"formatted_spent": pricing.format_amount(
			sum(flt(order.grand_total) for order in orders if order.status != "Cancelled")
		),
		"addresses": addresses(name),
		"reviews": reviews(primary_email),
	}


def addresses(customer: str) -> list[dict]:
	names = frappe.get_all(
		"Dynamic Link",
		filters={"parenttype": "Address", "link_doctype": "Customer", "link_name": customer},
		pluck="parent",
	)
	if not names:
		return []
	from frappe.contacts.doctype.address.address import get_address_display

	verifications = frappe.get_all(
		"Address",
		filters={"name": ["in", names]},
		fields=[
			"name",
			"custom_landmark",
			"custom_verification_status",
			"custom_address_risk_score",
			"custom_ors_confidence",
			"custom_gms_result_count",
			"custom_last_verified_on",
		],
	)
	by_name = {row.name: row for row in verifications}
	result = []
	for name in names:
		entry = {"name": name, "display": get_address_display(name)}
		row = by_name.get(name)
		if row:
			entry.update({
				"landmark": row.custom_landmark,
				"verification_status": row.custom_verification_status,
				"risk_score": row.custom_address_risk_score,
				"ors_confidence": row.custom_ors_confidence,
				"gms_result_count": row.custom_gms_result_count,
				"last_verified_on": str(row.custom_last_verified_on or ""),
			})
		result.append(entry)
	return result


def reviews(email: str | None) -> list[dict]:
	if not email:
		return []
	return frappe.get_all(
		"Shop Review",
		filters={"user": email},
		fields=["product", "rating", "title", "creation"],
		order_by="creation desc",
		limit=10,
	)
