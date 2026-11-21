"""The Google Merchant Center feed, built from real catalogue rows.

The feed is fetched by Google rather than rendered for a shopper, so the tests
look at the data that leaves the shop: one row per sellable item, the price the
product page shows, the stock in the configured warehouse, the brand from the
Item, and XML that survives an ampersand in the copy.
"""

import os
import xml.etree.ElementTree as ET

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import random_string
from frappe.utils.jinja import get_template

from shop.api import products, variants
from shop.integrations import google_merchant
from shop.storefront.returns import RETURN_WINDOW_DAYS
from shop.storefront.urls import SITE_BASE

NS = {"g": "http://base.google.com/ns/1.0"}


class TestGoogleMerchantHelpers(IntegrationTestCase):
	def test_gtin_check_digit_is_validated(self):
		# Known-valid EAN-13, UPC-A and EAN-8 codes.
		for code in ("4006381333931", "036000291452", "96385074"):
			self.assertEqual(google_merchant.valid_gtin(code), code, code)
		# Same length, wrong check digit.
		self.assertIsNone(google_merchant.valid_gtin("4006381333932"))
		# A shop barcode that is not a GTIN at all.
		self.assertIsNone(google_merchant.valid_gtin("ABC-123"))

	def test_feed_ids_stay_inside_googles_limit_and_do_not_collide(self):
		long_code = "A" * 80
		other = "A" * 79 + "B"
		first = google_merchant._feed_id(long_code)
		self.assertLessEqual(len(first), google_merchant.ID_LIMIT)
		self.assertTrue(first.startswith("g-"))
		self.assertEqual(first, google_merchant._feed_id(long_code))
		self.assertNotEqual(first, google_merchant._feed_id(other))
		self.assertEqual(google_merchant._feed_id("SHORT-CODE"), "SHORT-CODE")

	def test_condition_maps_to_merchant_centers_enum(self):
		self.assertEqual(google_merchant._condition("New"), "new")
		self.assertEqual(google_merchant._condition("Preloved"), "used")
		self.assertEqual(google_merchant._condition("Used - Good"), "used")
		self.assertEqual(google_merchant._condition("Refurbished"), "refurbished")
		self.assertEqual(google_merchant._condition(""), "new")
		self.assertEqual(google_merchant._condition("Vintage"), "used")

	def test_shipping_uses_the_rate_the_cart_actually_charges(self):
		settings = {
			"address_country": "Pakistan",
			"currency": "PKR",
			"flat_shipping_rate": 350,
			"shipping_account": "4120 - Service - ES",
		}
		self.assertEqual(
			google_merchant._shipping(settings),
			{"country": "PK", "service": "Standard", "price": "350.00 PKR"},
		)
		self.assertEqual(
			google_merchant._shipping({**settings, "shipping_account": None})["price"],
			"0.00 PKR",
		)
		self.assertIsNone(google_merchant._shipping({**settings, "address_country": ""}))

	def test_free_shipping_threshold_is_the_shop_order_total(self):
		settings = {
			"address_country": "Pakistan",
			"currency": "PKR",
			"free_shipping_above": 10000,
			"shipping_account": "4120 - Service - ES",
		}
		self.assertEqual(
			google_merchant._free_shipping_threshold(settings),
			{"country": "PK", "price_threshold": "10000.00 PKR"},
		)
		self.assertIsNone(google_merchant._free_shipping_threshold({**settings, "free_shipping_above": 0}))
		self.assertIsNone(google_merchant._free_shipping_threshold({**settings, "shipping_account": None}))
		self.assertIsNone(google_merchant._free_shipping_threshold({**settings, "address_country": ""}))

	def test_returns_use_the_configured_window_or_the_enforced_one(self):
		settings = {
			"address_country": "Pakistan",
			"currency": "PKR",
			"return_window_days": 30,
			"flat_shipping_rate": 350,
		}
		returns = google_merchant._returns(settings, "new")
		self.assertEqual(returns["country"], "PK")
		self.assertEqual(returns["item_condition"], "NEW")
		self.assertEqual(returns["window_days"], 30)
		self.assertEqual(returns["method"], "BY_MAIL")
		self.assertEqual(returns["shipping_fee"], "350.00 PKR")
		self.assertEqual(returns["shipping_fee_type"], "CUSTOMER_RESPONSIBILITY")
		fallback = google_merchant._returns({**settings, "return_window_days": 0}, "used")
		self.assertEqual(fallback["window_days"], RETURN_WINDOW_DAYS)
		self.assertEqual(fallback["item_condition"], "USED")
		self.assertIsNone(google_merchant._returns({**settings, "address_country": ""}, "new"))

	def test_plain_text_keeps_the_copy_and_drops_the_markup(self):
		text = google_merchant._plain_text("<p>Soft &amp; warm.</p><p>Second line.</p>")
		self.assertEqual(text, "Soft & warm.\n\nSecond line.")

	def test_text_sanitizing_drops_characters_xml_cannot_carry(self):
		# A control character copied out of a supplier spreadsheet, and a
		# zero-width joiner pasted in with emoji: neither is legal feed text.
		self.assertEqual(google_merchant._clean("Nike\u0000 Air\u200b Max"), "Nike Air Max")
		self.assertEqual(google_merchant._clean("  Plain text  "), "Plain text")
		self.assertEqual(google_merchant._fit("A\u0007B", 150), "AB")

	def test_xml_template_escapes_merchant_copy(self):
		xml = get_template("www/google_merchant_feed.xml").render(
			feed={"title": "A & B", "link": "https://reloop.pk/", "description": "<feed>"},
			items=[
				{
					"id": "1",
					"title": "Tom & Jerry <b>",
					"description": 'He said "yes" & left < 3',
					"link": "https://reloop.pk/product/x",
					"image_link": "https://reloop.pk/files/x.jpg",
					"price": "1.00 PKR",
					"availability": "in_stock",
					"condition": "new",
					"brand": "A & B",
					"identifier_exists": "no",
					"returns": {
						"country": "PK",
						"item_condition": "NEW",
						"window_days": 14,
						"window_type": "FINITE_RETURN_WINDOW",
						"method": "BY_MAIL",
						"outcome": "REFUND",
						"shipping_fee": "350.00 PKR",
						"shipping_fee_type": "CUSTOMER_RESPONSIBILITY",
					},
				}
			],
			shipping=None,
			free_shipping_threshold={"country": "PK", "price_threshold": "10000.00 PKR"},
			google_product_category="",
		)
		root = ET.fromstring(xml)
		self.assertEqual(root.find("channel/title").text, "A & B")
		self.assertEqual(root.find(".//g:title", NS).text, "Tom & Jerry <b>")
		self.assertEqual(root.find(".//g:description", NS).text, 'He said "yes" & left < 3')
		self.assertEqual(root.find(".//g:brand", NS).text, "A & B")
		returns = root.find(".//g:returns", NS)
		self.assertEqual(returns.find("g:window_days", NS).text, "14")
		self.assertEqual(returns.find("g:item_condition", NS).text, "NEW")
		self.assertEqual(returns.find("g:shipping_fee", NS).text, "350.00 PKR")
		self.assertEqual(returns.find("g:shipping_fee_type", NS).text, "CUSTOMER_RESPONSIBILITY")
		threshold = root.find(".//g:free_shipping_threshold", NS)
		self.assertEqual(threshold.find("g:country", NS).text, "PK")
		self.assertEqual(threshold.find("g:price_threshold", NS).text, "10000.00 PKR")


class TestGoogleMerchantFeed(IntegrationTestCase):
	def setUp(self):
		self.collection = self._make_collection()
		self.addCleanup(self._remove_collection)
		self.image, self.image_path = self._make_image()
		self.addCleanup(self._remove_image)

	def _make_collection(self):
		title = f"Feed Test Collection {random_string(6)}"
		return frappe.get_doc(
			{
				"doctype": "Shop Collection",
				"title": title,
				"slug": frappe.scrub(title),
				"published": 1,
			}
		).insert(ignore_permissions=True)

	def _remove_collection(self):
		if frappe.db.exists("Shop Collection", self.collection.name):
			frappe.delete_doc(
				"Shop Collection", self.collection.name, ignore_permissions=True, force=True
			)

	def _make_image(self):
		from PIL import Image

		name = f"google-merchant-test-{random_string(8)}.jpg"
		path = frappe.get_site_path("public", "files", name)
		Image.new("RGB", (8, 8), "white").save(path, "JPEG")
		return f"/files/{name}", path

	def _remove_image(self):
		if os.path.exists(self.image_path):
			os.remove(self.image_path)

	def _make_simple(self, **overrides):
		name = f"Feed Test Shoe {random_string(6)}"
		payload = {
			"product_name": name,
			"price": 5000,
			"compare_at_price": 7000,
			"condition": "Preloved",
			"brand": "Nike",
			"opening_stock": 2,
			"description": "<p>Soft &amp; warm.</p><p>Second line.</p>",
			"images": [self.image],
			"collections": [self.collection.name],
		}
		payload.update(overrides)
		result = products.create_product(**payload)
		self.addCleanup(self._remove_product, result["name"])
		return result

	def _make_variant(self):
		name = f"Feed Test Variant {random_string(6)}"
		result = variants.create_variant_product(
			product_name=name,
			options=[{"attribute": "Size", "values": ["40", "42"]}],
			price=8000,
			opening_stock=3,
			condition="New",
			brand="Adidas",
			images=[self.image],
			collections=[self.collection.name],
		)
		self.addCleanup(self._remove_product, result["product"])
		return result

	def _remove_product(self, product_name):
		item = frappe.db.get_value("Shop Product", product_name, "item")
		image_urls = frappe.get_all(
			"Shop Product Image", filters={"parent": product_name}, pluck="image"
		)
		if frappe.db.exists("Shop Product", product_name):
			products.delete_product(product_name)
		for url in image_urls:
			if url and url.startswith("/files/"):
				path = frappe.get_site_path("public", url.lstrip("/"))
				if os.path.isfile(path):
					os.remove(path)
		if not item:
			return
		codes = frappe.get_all("Item", filters={"variant_of": item}, pluck="name")
		codes.append(item)
		for code in codes:
			if frappe.db.exists("Item", code):
				frappe.delete_doc("Item", code, ignore_permissions=True, force=True)

	def _items(self):
		return {item["id"]: item for item in google_merchant.feed_context()["items"]}

	def test_a_simple_product_carries_the_storefront_price_stock_and_brand(self):
		result = self._make_simple()
		item = self._items()[result["item"]]

		self.assertEqual(item["title"], result["product_name"])
		self.assertEqual(item["description"], "Soft & warm.\n\nSecond line.")
		self.assertEqual(item["link"], f"{SITE_BASE}/product/{result['slug']}")
		self.assertTrue(item["image_link"].startswith(f"{SITE_BASE}/files/"))
		self.assertTrue(item["image_link"].endswith(".jpg"))
		self.assertEqual(item["price"], "7000.00 PKR")
		self.assertEqual(item["sale_price"], "5000.00 PKR")
		self.assertEqual(item["availability"], "in_stock")
		self.assertEqual(item["condition"], "used")
		self.assertEqual(item["brand"], "Nike")
		self.assertEqual(item["identifier_exists"], "no")
		self.assertNotIn("item_group_id", item)
		self.assertEqual(item["product_type"], self.collection.title)
		self.assertEqual(item["returns"]["item_condition"], "USED")
		self.assertEqual(item["returns"]["window_days"], RETURN_WINDOW_DAYS)

	def test_a_sold_out_product_is_out_of_stock(self):
		previous = frappe.db.get_single_value("Shop Settings", "allow_out_of_stock")
		frappe.db.set_single_value("Shop Settings", "allow_out_of_stock", 0)
		self.addCleanup(frappe.clear_cache)
		self.addCleanup(
			frappe.db.set_single_value, "Shop Settings", "allow_out_of_stock", previous
		)
		frappe.clear_cache()

		result = self._make_simple(opening_stock=0)
		self.assertEqual(self._items()[result["item"]]["availability"], "out_of_stock")

	def test_variants_are_separate_rows_in_one_group_with_size_and_colour(self):
		result = self._make_variant()
		template = frappe.db.get_value("Shop Product", result["product"], "item")
		codes = frappe.get_all("Item", filters={"variant_of": template}, pluck="name")
		self.assertEqual(len(codes), 2)

		items = self._items()
		for code in codes:
			item = items[code]
			self.assertEqual(item["item_group_id"], template)
			self.assertEqual(item["brand"], "Adidas")
			self.assertEqual(item["condition"], "new")
			self.assertEqual(item["availability"], "in_stock")
			self.assertEqual(item["price"], "8000.00 PKR")
			self.assertNotIn("sale_price", item)
			self.assertIn(item["size"], {"40", "42"})
			self.assertIn(f"Size {item['size']}", item["title"])
			self.assertEqual(item["returns"]["item_condition"], "NEW")

		self.assertEqual(len({items[code]["title"] for code in codes}), 2)

	def test_a_valid_barcode_becomes_a_gtin_and_a_missing_one_does_not(self):
		result = self._make_simple()
		item = self._items()[result["item"]]
		self.assertNotIn("gtin", item)
		self.assertEqual(item["identifier_exists"], "no")

		frappe.get_doc(
			{
				"doctype": "Item Barcode",
				"parent": result["item"],
				"parenttype": "Item",
				"parentfield": "barcodes",
				"barcode": "4006381333931",
				"barcode_type": "EAN",
			}
		).insert(ignore_permissions=True)

		item = self._items()[result["item"]]
		self.assertEqual(item["gtin"], "4006381333931")
		self.assertNotIn("identifier_exists", item)
