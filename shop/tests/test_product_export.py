"""The product CSV is a hand-off to a Marketplace import.

Only the products the merchant ticked leave the shop, in the order they were
picked, with the columns a Marketplace expects. These tests build a product
or two, read the file back, and take everything they made off the books.
"""

import csv
import io

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import get_url, random_string

from shop.api import products, variants

SIZES = [{"attribute": "Size", "values": ["40", "42", "40.5"]}]


class TestProductExport(IntegrationTestCase):
	def setUp(self):
		self.collection = self._make_collection()
		self.addCleanup(self._remove_collection)

	def _make_collection(self):
		title = f"CSV Export Collection {random_string(6)}"
		collection = frappe.get_doc(
			{
				"doctype": "Shop Collection",
				"title": title,
				"slug": frappe.scrub(title),
				"published": 1,
			}
		).insert(ignore_permissions=True)
		return collection

	def _remove_collection(self):
		if frappe.db.exists("Shop Collection", self.collection.name):
			frappe.delete_doc(
				"Shop Collection", self.collection.name, ignore_permissions=True, force=True
			)

	def make_simple(self, label="CSV Export Tee", description=None):
		name = f"{label} {random_string(6)}"
		result = products.create_product(
			product_name=name,
			price=1250.5,
			description=description or "<p>Soft &amp; warm.</p><p>Second line.</p>",
			short_description="Soft and warm",
			condition="Preloved",
			images=["/files/csv-export-test-1.jpg", "/files/csv-export-test-2.jpg"],
			collections=[self.collection.name],
		)
		self.addCleanup(self._remove_product, result["name"], name)
		return result

	def make_variant(self, label="CSV Export Variant"):
		name = f"{label} {random_string(6)}"
		result = variants.create_variant_product(
			product_name=name,
			options=SIZES,
			price=700,
			condition="New",
			collections=[self.collection.name],
		)
		self.addCleanup(self._remove_product, result["product"], name)
		return result

	def _remove_product(self, product_name, item_name):
		if frappe.db.exists("Shop Product", product_name):
			products.delete_product(product_name)
		codes = frappe.get_all(
			"Item", filters={"item_name": ["like", f"{item_name}%"]}, pluck="name"
		)
		for code in codes:
			if frappe.db.exists("Item", code):
				frappe.delete_doc("Item", code, ignore_permissions=True, force=True)

	def read_csv(self, content):
		return list(csv.DictReader(io.StringIO(content)))

	def test_only_the_selected_products_are_exported_in_order(self):
		first = self.make_simple("CSV Export First")
		second = self.make_simple("CSV Export Second")

		rows = self.read_csv(products.build_export_csv([second["name"], first["name"]]))

		self.assertEqual([row["Title"] for row in rows], [second["product_name"], first["product_name"]])

	def test_the_header_and_price_are_written_as_the_sample_has_them(self):
		product = self.make_simple()
		content = products.build_export_csv([product["name"]])

		self.assertEqual(
			content.split("\r\n")[0],
			"Title,Price,Category,Condition,Description,Size,Material,Images",
		)
		self.assertIn(f'"{product["product_name"]}",1250.5,', content)

	def test_fields_come_from_the_product(self):
		product = self.make_simple()
		row = self.read_csv(products.build_export_csv([product["name"]]))[0]

		self.assertEqual(row["Price"], "1250.5")
		self.assertEqual(row["Category"], self.collection.title)
		self.assertEqual(row["Condition"], "Used - Good")
		self.assertEqual(row["Description"], "Soft & warm. Second line.")
		self.assertEqual(row["Size"], "")
		self.assertEqual(row["Material"], "")
		self.assertEqual(
			row["Images"].split(", "),
			[
				get_url("/files/csv-export-test-1.jpg"),
				get_url("/files/csv-export-test-2.jpg"),
			],
		)

	def test_variant_sizes_are_listed_once_each_in_a_readable_order(self):
		product = self.make_variant()
		row = self.read_csv(products.build_export_csv([product["product"]]))[0]

		self.assertEqual(row["Size"], "40, 40.5, 42")

	def test_a_price_of_whole_rupees_has_no_decimal_point(self):
		product = self.make_variant()
		row = self.read_csv(products.build_export_csv([product["product"]]))[0]

		self.assertEqual(row["Price"], "700")

	def test_a_title_with_a_comma_and_a_quote_survives_the_round_trip(self):
		product = self.make_simple('CSV "Quoted", Tee')
		row = self.read_csv(products.build_export_csv([product["name"]]))[0]

		self.assertEqual(row["Title"], product["product_name"])

	def test_nothing_selected_is_an_error(self):
		with self.assertRaises(frappe.ValidationError):
			products.build_export_csv([])
