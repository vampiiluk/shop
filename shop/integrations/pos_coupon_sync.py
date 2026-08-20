import frappe
from frappe.utils import flt

RULE_PREFIX = "Shop coupon"


def pos_coupon_available() -> bool:
	"""True when the posnext POS Coupon doctype exists on this bench."""
	return frappe.db.table_exists("POS Coupon")


def _rule_title(code: str) -> str:
	return f"{RULE_PREFIX} {code}"


def _default_company() -> str:
	company = frappe.db.get_single_value("Shop Settings", "company")
	if company:
		return company
	return frappe.db.get_value("Company", {"is_group": 0}, "name", order_by="creation")


def _upsert_rule_for_pos_coupon(doc, code: str) -> str:
	existing = None
	if doc.pricing_rule and frappe.db.get_value("Pricing Rule", doc.pricing_rule, "title") == _rule_title(code):
		existing = doc.pricing_rule
	if not existing:
		existing = frappe.db.get_value("Pricing Rule", {"title": _rule_title(code), "coupon_code_based": 1})
	rule = frappe.get_doc("Pricing Rule", existing) if existing else frappe.new_doc("Pricing Rule")
	rule.title = _rule_title(code)
	rule.apply_on = "Transaction"
	rule.price_or_product_discount = "Price"
	rule.selling = 1
	rule.coupon_code_based = 1
	rule.company = doc.company or _default_company()
	rule.apply_discount_on = doc.apply_on or "Grand Total"
	rule.disable = 1 if doc.disabled else 0
	rule.min_amt = flt(doc.min_amount)
	if doc.discount_type == "Amount":
		rule.rate_or_discount = "Discount Amount"
		rule.discount_amount = flt(doc.discount_amount)
		rule.discount_percentage = 0
	else:
		rule.rate_or_discount = "Discount Percentage"
		rule.discount_percentage = flt(doc.discount_percentage)
		rule.discount_amount = 0
	if existing:
		rule.save(ignore_permissions=True)
	else:
		rule.insert(ignore_permissions=True)
	return rule.name


def sync_pos_coupon_to_erpnext(doc, method=None):
	"""POS Coupon -> Coupon Code + Pricing Rule so the storefront honors the code."""
	if not pos_coupon_available() or doc.doctype != "POS Coupon":
		return
	if doc.coupon_type != "Promotional":
		return
	code = (doc.coupon_code or "").strip().upper()
	if not code:
		return

	rule = _upsert_rule_for_pos_coupon(doc, code)
	existing = frappe.db.get_value("Coupon Code", {"coupon_code": code})
	coupon = frappe.get_doc("Coupon Code", existing) if existing else frappe.new_doc("Coupon Code")
	coupon.coupon_name = doc.coupon_name or code
	coupon.coupon_type = "Promotional"
	coupon.coupon_code = code
	coupon.pricing_rule = rule
	coupon.valid_from = doc.valid_from or None
	coupon.valid_upto = doc.valid_upto or None
	coupon.maximum_use = doc.maximum_use or 0
	if existing:
		coupon.save(ignore_permissions=True)
	else:
		coupon.insert(ignore_permissions=True)


def write_pos_coupon_links(doc, method=None):
	"""After a POS Coupon is saved, fill the dormant integration links on it."""
	if not pos_coupon_available() or doc.doctype != "POS Coupon":
		return
	if doc.coupon_type != "Promotional":
		return
	code = (doc.coupon_code or "").strip().upper()
	if not code:
		return
	coupon_name = frappe.db.get_value("Coupon Code", {"coupon_code": code})
	if not coupon_name:
		return
	rule_name = frappe.db.get_value("Coupon Code", coupon_name, "pricing_rule")
	frappe.db.set_value(
		"POS Coupon",
		doc.name,
		{"erpnext_coupon_code": coupon_name, "pricing_rule": rule_name},
		update_modified=False,
	)


def sync_erpnext_coupon_to_pos(coupon, rule):
	"""Coupon Code + Pricing Rule -> POS Coupon so the POS honors the code."""
	if not pos_coupon_available():
		return None
	code = (coupon.coupon_code or "").strip().upper()
	if not code:
		return None
	existing = frappe.db.get_value("POS Coupon", {"coupon_code": code})
	pos = frappe.get_doc("POS Coupon", existing) if existing else frappe.new_doc("POS Coupon")
	pos.coupon_name = coupon.coupon_name or code
	pos.coupon_type = "Promotional"
	pos.coupon_code = code
	pos.company = rule.company or _default_company()
	pos.discount_type = "Amount" if rule.rate_or_discount == "Discount Amount" else "Percentage"
	pos.discount_percentage = flt(rule.discount_percentage)
	pos.discount_amount = flt(rule.discount_amount)
	pos.min_amount = flt(rule.min_amt)
	pos.apply_on = rule.apply_discount_on or "Grand Total"
	pos.valid_from = coupon.valid_from or None
	pos.valid_upto = coupon.valid_upto or None
	pos.maximum_use = coupon.maximum_use or 0
	pos.disabled = 1 if rule.disable else 0
	pos.erpnext_coupon_code = coupon.name
	pos.pricing_rule = rule.name
	if existing:
		pos.save(ignore_permissions=True)
	else:
		pos.insert(ignore_permissions=True)
	return pos.name


def release_from_carts(coupon_code_name: str) -> None:
	"""A coupon sitting in someone's cart must not make itself undeletable."""
	for cart in frappe.get_all("Shop Cart", filters={"coupon_code": coupon_code_name}, pluck="name"):
		frappe.db.set_value("Shop Cart", cart, "coupon_code", None, update_modified=False)


def delete_pos_coupon_from_erpnext(doc, method=None):
	"""POS Coupon on_trash -> remove the generated Coupon Code + Pricing Rule."""
	if not pos_coupon_available() or doc.doctype != "POS Coupon":
		return
	code = (doc.coupon_code or "").strip().upper()
	coupon_name = doc.erpnext_coupon_code
	if not coupon_name and code:
		coupon_name = frappe.db.get_value("Coupon Code", {"coupon_code": code})
	rule_name = doc.pricing_rule
	if coupon_name:
		if not rule_name:
			rule_name = frappe.db.get_value("Coupon Code", coupon_name, "pricing_rule")
		title = frappe.db.get_value("Pricing Rule", rule_name, "title") if rule_name else None
		frappe.db.set_value(
			"POS Coupon",
			doc.name,
			{"erpnext_coupon_code": None, "pricing_rule": None},
			update_modified=False,
		)
		release_from_carts(coupon_name)
		frappe.delete_doc("Coupon Code", coupon_name, ignore_permissions=True)
		if title and title.startswith(RULE_PREFIX):
			frappe.delete_doc("Pricing Rule", rule_name, ignore_permissions=True, force=True)
	elif rule_name:
		title = frappe.db.get_value("Pricing Rule", rule_name, "title")
		if title and title.startswith(RULE_PREFIX):
			frappe.delete_doc("Pricing Rule", rule_name, ignore_permissions=True, force=True)


def delete_erpnext_coupon_from_pos(coupon_code: str) -> None:
	"""Coupon Code delete -> remove the mirrored POS Coupon (Promotional only)."""
	if not pos_coupon_available():
		return
	pos_name = frappe.db.get_value("POS Coupon", {"coupon_code": coupon_code})
	if pos_name:
		frappe.delete_doc("POS Coupon", pos_name, ignore_permissions=True, force=True)