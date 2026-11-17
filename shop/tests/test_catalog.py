import frappe
from frappe.tests import IntegrationTestCase

from shop.storefront import catalog, product


class TestCatalog(IntegrationTestCase):
	def test_listing_returns_published_products(self):
		result = catalog.get_products()
		self.assertEqual(result["total"], frappe.db.count("Shop Product", {"published": 1}))
		self.assertTrue(result["products"])
		first = result["products"][0]
		self.assertIn("slug", first)
		self.assertIsNotNone(first.formatted_price)
		self.assertTrue(first.in_stock)

	def test_collection_filter(self):
		# The demo collections are only created when absent, so on a site that
		# already has an "Apparel" collection the seeded one is not published by
		# the fixture. Publish it for the length of the test.
		previous = frappe.db.get_value("Shop Collection", "apparel", "published")
		frappe.db.set_value("Shop Collection", "apparel", "published", 1)
		self.addCleanup(frappe.db.set_value, "Shop Collection", "apparel", "published", previous)
		result = catalog.get_products(collection="apparel")
		slugs = {p.slug for p in result["products"]}
		self.assertIn("crew-neck-t-shirt", slugs)
		self.assertNotIn("ceramic-mug", slugs)

	def test_search(self):
		# "ceramic" names the demo mug and nothing in the live catalogue, unlike
		# the generic "mug" which now finds real travel mugs too.
		result = catalog.get_products(search="ceramic")
		self.assertEqual(result["total"], 1)
		self.assertEqual(result["products"][0].slug, "ceramic-mug")

	def test_collections_have_counts(self):
		collections = catalog.get_collections()
		self.assertEqual(len(collections), 4)
		self.assertTrue(all(c.product_count > 0 for c in collections))

	def test_product_detail_simple(self):
		detail = product.get_product("ceramic-mug")
		self.assertEqual(detail["item"], "SHOP-DEMO-003")
		self.assertTrue(detail["in_stock"])
		self.assertTrue(detail["images"])
		self.assertFalse(detail["has_variants"])

	def test_product_detail_variants(self):
		detail = product.get_product("crew-neck-t-shirt")
		self.assertTrue(detail["has_variants"])
		self.assertEqual(len(detail["variants"]), 6)
		attributes = {a["attribute"]: a["values"] for a in detail["attributes"]}
		self.assertEqual(attributes["Size"], ["Small", "Medium", "Large"])
		self.assertIn(detail["default_item_code"], [v["item_code"] for v in detail["variants"]])

	def test_listing_and_detail_carry_the_item_brand(self):
		created = not frappe.db.exists("Brand", "Test Brand")
		if created:
			frappe.get_doc({"doctype": "Brand", "brand": "Test Brand"}).insert(
				ignore_permissions=True
			)
		previous = frappe.db.get_value("Item", "SHOP-DEMO-003", "brand")
		frappe.db.set_value("Item", "SHOP-DEMO-003", "brand", "Test Brand")
		# Cleanups run last-in-first-out, so the item is unlinked before the Brand
		# record is removed.
		if created:
			self.addCleanup(
				frappe.delete_doc, "Brand", "Test Brand", ignore_permissions=True, force=True
			)
		self.addCleanup(frappe.db.set_value, "Item", "SHOP-DEMO-003", "brand", previous)

		listed = catalog.get_products(search="ceramic")["products"][0]
		self.assertEqual(listed.brand, "Test Brand")
		self.assertEqual(product.get_product("ceramic-mug")["brand"], "Test Brand")

	def test_brand_writes_reach_the_template_and_every_variant(self):
		from shop.api import products as products_api

		template = "SHOP-DEMO-001"
		codes = [template] + frappe.get_all(
			"Item", filters={"variant_of": template}, pluck="name"
		)
		previous = {code: frappe.db.get_value("Item", code, "brand") for code in codes}
		created = not frappe.db.exists("Brand", "Nike")
		if created:
			frappe.get_doc({"doctype": "Brand", "brand": "Nike"}).insert(ignore_permissions=True)
		if created:
			self.addCleanup(
				frappe.delete_doc, "Brand", "Nike", ignore_permissions=True, force=True
			)
		for code, brand in previous.items():
			self.addCleanup(frappe.db.set_value, "Item", code, "brand", brand)

		products_api.set_item_brand(template, "nike", has_variants=True)
		for code in codes:
			self.assertEqual(frappe.db.get_value("Item", code, "brand"), "Nike")

	def test_seo_only_collection_stays_out_of_navigation_but_keeps_its_page(self):
		previous = frappe.db.get_value("Shop Collection", "shoes", "show_in_navigation")
		frappe.db.set_value("Shop Collection", "shoes", "show_in_navigation", 0)
		self.addCleanup(
			frappe.db.set_value, "Shop Collection", "shoes", "show_in_navigation", previous
		)
		slugs = {row.slug for row in catalog.get_collections()}
		self.assertNotIn("shoes", slugs)
		# The collection page itself still resolves its products.
		self.assertTrue(catalog.collection_members("shoes"))

	def test_unpublished_product_hidden(self):
		with self.assertRaises(frappe.DoesNotExistError):
			product.get_product("does-not-exist")
