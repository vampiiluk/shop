import json

import frappe
from frappe.tests import IntegrationTestCase

from shop.storefront import seo


class TestCollectionSeo(IntegrationTestCase):
	COLLECTION = {"title": "Shoes", "slug": "shoes", "description": ""}

	def graph(self, result: dict) -> list[dict]:
		html = result["_head_html"]
		payload = html[html.index(">") + 1 : html.rindex("</script>")]
		return json.loads(payload)["@graph"]

	def test_title_uses_the_collection_not_the_generic_shop_label(self):
		result = seo.seo_for("collection/shoes", collection=self.COLLECTION)
		self.assertIn("Shoes in Pakistan", result["title"])
		self.assertIn("Preloved", result["title"])
		self.assertNotIn("Shop —", result["title"])

	def test_description_falls_back_to_a_useful_sentence_when_blank(self):
		result = seo.seo_for("collection/shoes", collection=self.COLLECTION)
		self.assertIn("cash on delivery", result["metatags"]["description"])
		self.assertIn("Pakistan", result["metatags"]["description"])

	def test_description_keeps_the_collection_copy(self):
		collection = {**self.COLLECTION, "title": "Bags", "description": "Style you can carry."}
		result = seo.seo_for("collection/bags", collection=collection)
		self.assertTrue(result["metatags"]["description"].startswith("Style you can carry."))

	def test_breadcrumb_names_the_collection_not_the_full_page_title(self):
		result = seo.seo_for("collection/shoes", collection=self.COLLECTION)
		crumbs = next(node for node in self.graph(result) if node["@type"] == "BreadcrumbList")
		self.assertEqual(crumbs["itemListElement"][-1]["name"], "Shoes")

	def test_collection_page_node_is_emitted(self):
		result = seo.seo_for("collection/shoes", collection=self.COLLECTION)
		nodes = [node["@type"] for node in self.graph(result)]
		self.assertIn("CollectionPage", nodes)
		self.assertNotIn("Product", nodes)

	def test_canonical_is_unchanged(self):
		result = seo.seo_for("collection/shoes", collection=self.COLLECTION)
		self.assertEqual(result["canonical_url"], seo.site_url("/collection/shoes"))
		self.assertEqual(result["metatags"]["og:url"], result["canonical_url"])


class TestProductStructuredData(IntegrationTestCase):
	def node(self, **overrides) -> dict:
		product = {
			"name": "test-product",
			"product_name": "Nike Flex Contact 3",
			"route": "/product/nike-flex-contact-3",
			"brand": "Nike",
			"condition": "Preloved",
			"price": 5000,
			"in_stock": False,
			**overrides,
		}
		return seo._product_node(product, seo.store_settings())

	def test_a_preloved_product_is_used_not_new(self):
		node = self.node()
		self.assertEqual(node["itemCondition"], "https://schema.org/UsedCondition")

	def test_a_new_product_is_new_condition(self):
		node = self.node(condition="New")
		self.assertEqual(node["itemCondition"], "https://schema.org/NewCondition")

	def test_a_marketplace_used_grade_is_used_condition(self):
		node = self.node(condition="Used - Good")
		self.assertEqual(node["itemCondition"], "https://schema.org/UsedCondition")

	def test_an_unrecognised_condition_is_not_guessed(self):
		node = self.node(condition="Vintage")
		self.assertNotIn("itemCondition", node)

	def test_a_blank_condition_is_not_guessed(self):
		node = self.node(condition="")
		self.assertNotIn("itemCondition", node)

	def test_the_condition_never_becomes_the_brand(self):
		node = self.node(condition="Preloved", brand="")
		self.assertNotIn("brand", node)

	def test_a_real_brand_is_emitted(self):
		node = self.node(condition="New", brand="Nike")
		self.assertEqual(node["brand"], {"@type": "Brand", "name": "Nike"})


class TestOfferCatalog(IntegrationTestCase):
	def test_catalog_covers_more_than_one_api_page(self):
		"""A single get_products call stops at 60; the graph must page past it."""
		published = frappe.db.count("Shop Product", {"published": 1})
		products = seo._catalog_products(seo.CATALOG_LIMIT)
		self.assertEqual(len(products), min(published, seo.CATALOG_LIMIT))
		self.assertEqual(len({p.name for p in products}), len(products))
