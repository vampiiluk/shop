"""The order the desk shows: what the line is, and how it is paid.

Two things were missing. A variant's own name is a code with the size on
the end - "CMP ALKHESTE LOW-414" - which tells a customer nothing about
what they ordered, so the product's name is shown with the size or colour
under it. And a merchant taking a payment at the counter may be asked for
either the advance or the whole total, so both codes are drawn for them.
"""

import unittest

import frappe
from frappe.tests import IntegrationTestCase

from shop.api.orders import get_order
from shop.api.products import item_labels
from shop.tests import force_cod_enabled


class TestItemLabels(IntegrationTestCase):
	def test_a_variant_is_named_by_its_product_and_its_attributes(self):
		"""A variant shows the product's name, and the size or colour under it."""
		from shop.storefront import stock

		product = None
		for row in frappe.get_all(
			"Shop Product", filters={"published": 1, "has_variants": 1}, fields=["name", "item"], limit=20
		):
			codes = frappe.get_all("Item", filters={"variant_of": row.item}, pluck="name")
			if not codes:
				continue
			attributes = frappe.get_all(
				"Item Variant Attribute",
				filters={"parent": ["in", codes]},
				fields=["parent", "attribute", "attribute_value"],
				order_by="idx",
			)
			if any(a.attribute_value for a in attributes):
				product = (row, codes)
				break
		if not product:
			self.skipTest("this site has no published product that varies")

		row, codes = product
		names, attributes = item_labels(codes)

		# The name is the product's, not the variant's code with the size on
		# the end.
		parent_name = frappe.db.get_value("Item", row.item, "item_name")
		self.assertEqual(names[codes[0]], parent_name)

		# And the attributes that pick the variant are named.
		chosen = [a for a in attributes.get(codes[0], []) if a]
		self.assertTrue(chosen)
		self.assertIn("Size", chosen[0])

	def test_a_plain_item_keeps_its_own_name(self):
		from shop.storefront import stock

		for row in frappe.get_all(
			"Shop Product", filters={"published": 1, "has_variants": 0}, fields=["item"], limit=5
		):
			names, attributes = item_labels([row.item])
			self.assertEqual(names[row.item], frappe.db.get_value("Item", row.item, "item_name"))
			# Nothing to say about it: a plain item has no attributes.
			self.assertFalse(attributes.get(row.item))
			return
		self.skipTest("this site has no published plain product")


class TestPaymentCodes(IntegrationTestCase):
	def setUp(self):
		force_cod_enabled(self)

	def _order(self):
		"""A real order to draw codes for."""
		for row in frappe.get_all(
			"Shop Product", filters={"published": 1, "has_variants": 0}, fields=["item"], limit=20
		):
			if frappe.db.get_value("Item", row.item, "disabled"):
				continue
			return frappe.get_doc(
				{
					"doctype": "Sales Order",
					"company": frappe.db.get_single_value("Shop Settings", "company"),
					"customer": frappe.db.get_value("Customer", {"customer_type": "Individual"}, "name"),
					"selling_price_list": frappe.db.get_single_value("Shop Settings", "price_list"),
					"currency": frappe.db.get_single_value("Shop Settings", "currency"),
					"delivery_date": frappe.utils.add_days(frappe.utils.nowdate(), 3),
					"conversion_rate": 1,
					"plc_conversion_rate": 1,
					"items": [{"item_code": row.item, "qty": 1, "rate": 1000}],
				}
			).insert(ignore_permissions=True)
		self.skipTest("this site has no published plain product")

	def test_both_codes_are_drawn_for_an_order(self):
		from shop import payments

		if not payments.configured():
			self.skipTest("this site has no payment account configured")

		order = self._order()
		try:
			doc = get_order(order.name)
			codes = doc["payment_qrs"]
			self.assertTrue(codes, "the desk needs a code to take a payment with")

			stages = {code["stage"] for code in codes}
			self.assertIn("full", stages)
			self.assertIn("advance", stages)

			for code in codes:
				# The code is a real PNG carrying the figure it is for.
				self.assertTrue(code["qr_data_url"].startswith("data:image/png;base64,"))
				self.assertTrue(code["payload"])
				self.assertIn(str(int(code["amount"])), code["payload"])
				# And it says which order it settles, so a saved card can
				# be reconciled later.
				self.assertIn(order.name, code["download_name"])
		finally:
			frappe.delete_doc("Sales Order", order.name, force=True, ignore_permissions=True)
