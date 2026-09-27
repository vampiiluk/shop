import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from shop.storefront import pricing


def resolve(code: str) -> dict:
	"""Validate a coupon code and return its discount terms. Throws on any problem."""
	name = frappe.db.get_value("Coupon Code", {"coupon_code": code.strip()})
	if not name:
		frappe.throw(_("That coupon code is not valid"))
	coupon = frappe.db.get_value(
		"Coupon Code",
		name,
		["name", "coupon_code", "pricing_rule", "valid_from", "valid_upto", "maximum_use", "used"],
		as_dict=True,
	)
	today = getdate(nowdate())
	if coupon.valid_from and getdate(coupon.valid_from) > today:
		frappe.throw(_("That coupon is not active yet"))
	if coupon.valid_upto and getdate(coupon.valid_upto) < today:
		frappe.throw(_("That coupon has expired"))
	if coupon.maximum_use and coupon.used >= coupon.maximum_use:
		frappe.throw(_("That coupon has been fully redeemed"))
	rule = frappe.db.get_value(
		"Pricing Rule",
		coupon.pricing_rule,
		["disable", "rate_or_discount", "discount_percentage", "discount_amount", "min_amt"],
		as_dict=True,
	)
	if not rule or rule.disable:
		frappe.throw(_("That coupon code is not valid"))
	max_amount = 0
	if frappe.db.table_exists("POS Coupon"):
		max_amount = flt(
			frappe.db.get_value("POS Coupon", {"coupon_code": coupon.coupon_code}, "max_amount") or 0
		)
	return frappe._dict(
		name=coupon.name,
		code=coupon.coupon_code,
		rate_or_discount=rule.rate_or_discount,
		discount_percentage=flt(rule.discount_percentage),
		discount_amount=flt(rule.discount_amount),
		min_amt=flt(rule.min_amt),
		max_amount=max_amount,
	)


def discount_for(coupon: dict, subtotal: float) -> float:
	if coupon.min_amt and subtotal < coupon.min_amt:
		frappe.throw(
			_("Add items worth {0} to use this coupon").format(pricing.format_amount(coupon.min_amt))
		)
	if coupon.rate_or_discount == "Discount Percentage":
		discount = flt(subtotal * coupon.discount_percentage / 100, 2)
	else:
		discount = min(flt(coupon.discount_amount), subtotal)
	if coupon.max_amount:
		discount = min(discount, flt(coupon.max_amount))
	return discount


def redeem(name: str):
	"""Count one redemption — atomically against the cap.

	resolve() is a friendly answer for the apply button; it is not the guard.
	Two requests that both read used=9 < 10 both pass it, which used to let a
	last-chance coupon redeem twice — with the decision and the write sharing
	one locked row, exactly maximum_use redemptions can ever succeed and every
	late one throws here, before the request commits its just-created order.
	"""
	frappe.db.sql(
		"""
		UPDATE `tabCoupon Code`
		   SET used = COALESCE(used, 0) + 1
		 WHERE name = %s
		   AND (COALESCE(maximum_use, 0) = 0 OR COALESCE(used, 0) < maximum_use)
		""",
		name,
	)
	if frappe.db.sql("SELECT ROW_COUNT() AS n", as_dict=True)[0]["n"] != 1:
		frappe.throw(_("That coupon has been fully redeemed"))
