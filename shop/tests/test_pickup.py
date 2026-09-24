import frappe
from frappe.tests import IntegrationTestCase

from shop.api import settings as settings_api
from shop.storefront import cart, checkout, pricing

BUYER = {"email": "jane@example.com", "full_name": "Jane Doe", "phone": "9999966666"}
ADDRESS = {
	"address_line1": "12 Lake View Road",
	"city": "Bengaluru",
	"state": "Karnataka",
	"country": "India",
	"pincode": "560001",
	"landmark": "Gate 7",
}
LOCATION = {
	"location_name": "Main Store",
	"address": "1 Station Road, Rahim Yar Khan",
	"latitude": "29.1044",
	"longitude": "70.3298",
	"phone": "03001234567",
}


class TestPickup(IntegrationTestCase):
	def setUp(self):
		frappe.db.delete("Shop Cart")
		if hasattr(frappe.local, "request"):
			del frappe.local.request
		previous_fraud = frappe.db.get_single_value("Shop Settings", "enable_fraud_check")
		frappe.db.set_single_value("Shop Settings", "enable_fraud_check", 0)
		self.previous_provider = frappe.db.get_single_value("Shop Settings", "map_embed_provider")
		self.previous_enable = frappe.db.get_single_value("Shop Settings", "enable_pickup")
		self.previous_locations = [
			{
				"location_name": row.location_name,
				"address": row.address,
				"latitude": row.latitude,
				"longitude": row.longitude,
				"phone": row.phone,
			}
			for row in frappe.get_doc("Shop Settings").pickup_locations or []
		]
		frappe.get_cached_doc("Shop Settings")
		self.addCleanup(self._restore, previous_fraud)

	def _restore(self, previous_fraud):
		settings = frappe.get_doc("Shop Settings")
		settings.enable_pickup = self.previous_enable
		settings.pickup_locations = []
		for row in self.previous_locations:
			settings.append("pickup_locations", row)
		settings.save(ignore_permissions=True)
		frappe.db.set_single_value("Shop Settings", "enable_fraud_check", previous_fraud)
		frappe.db.set_single_value(
			"Shop Settings", "map_embed_provider", self.previous_provider or "OpenStreetMap"
		)
		frappe.get_cached_doc("Shop Settings")

	def _map_host(self) -> str:
		"""The embed host the store is currently configured to use."""
		provider = frappe.db.get_single_value("Shop Settings", "map_embed_provider")
		return "google.com" if provider == "Google Maps" else "openstreetmap.org"

	def _set_pickup(self, enabled: bool):
		settings = frappe.get_doc("Shop Settings")
		settings.enable_pickup = 1 if enabled else 0
		settings.pickup_locations = []
		if enabled:
			settings.append("pickup_locations", dict(LOCATION))
		settings.save(ignore_permissions=True)
		frappe.get_cached_doc("Shop Settings")

	def test_summary_lists_pickup_only_when_enabled(self):
		self._set_pickup(False)
		summary = checkout.get_checkout_summary()
		self.assertNotIn("pickup", [row["method"] for row in summary["payment_methods"]])
		self.assertIsNone(summary.get("pickup_locations"))
		self.assertIsNone(summary.get("pickup_view"))

		self._set_pickup(True)
		cart.add_item("SHOP-DEMO-003")
		summary = checkout.get_checkout_summary()
		self.assertIn("pickup", [row["method"] for row in summary["payment_methods"]])
		self.assertEqual(len(summary["pickup_locations"]), 1)
		row = summary["pickup_locations"][0]
		self.assertEqual(row["name"], LOCATION["location_name"])
		self.assertIn(self._map_host(), row["map_url"])
		self.assertIn(LOCATION["latitude"], row["map_url"])
		self.assertTrue(row["directions_url"])

		# The pickup totals view drops the shipping fee from the shown total.
		payload = summary["cart"]
		self.assertEqual(summary["pickup_view"]["formatted_shipping"], "Free")
		if payload.get("shipping"):
			expected = pricing.format_amount(payload["total"] - payload["shipping"])
			self.assertEqual(summary["pickup_view"]["formatted_total"], expected)

	def test_pickup_rejected_when_disabled_or_location_unknown(self):
		self._set_pickup(False)
		cart.add_item("SHOP-DEMO-003")
		with self.assertRaises(frappe.ValidationError):
			checkout.place_order(
				customer=BUYER, address=ADDRESS, payment_method="pickup", pickup_location=LOCATION["location_name"]
			)

		self._set_pickup(True)
		with self.assertRaises(frappe.ValidationError):
			checkout.place_order(customer=BUYER, address=ADDRESS, payment_method="pickup", pickup_location="Elsewhere")
		with self.assertRaises(frappe.ValidationError):
			checkout.place_order(customer=BUYER, address=ADDRESS, payment_method="pickup", pickup_location="")

	def test_place_order_pickup_waives_shipping_and_records_location(self):
		self._set_pickup(True)
		cart.add_item("SHOP-DEMO-003")
		result = checkout.place_order(
			customer=BUYER, address=ADDRESS, payment_method="pickup", pickup_location=LOCATION["location_name"]
		)
		sales_order = frappe.get_doc("Sales Order", result["sales_order"])
		self.assertEqual(sales_order.docstatus, 1)
		self.assertEqual(sales_order.get("custom_payment_method"), "pickup")
		self.assertEqual(sales_order.get("custom_pickup_location"), LOCATION["location_name"])
		# Pickup skips the courier: no shipping line, unlike a delivery order.
		shipping_rows = [tax for tax in sales_order.taxes if (tax.description or "").lower() == "shipping"]
		self.assertFalse(shipping_rows)
		# Confirmation data carries the chosen location with its map.
		summary = orders_summary(sales_order)
		self.assertEqual(summary["payment_method"], "pickup")
		self.assertEqual(summary["pickup_location"]["name"], LOCATION["location_name"])
		self.assertIn(self._map_host(), summary["pickup_location"]["map_url"])
		# No courier means no "ships in 48 hours" hint on the confirmation page.
		self.assertFalse(summary["awaiting_shipment"])
		labels = [stage["label"] for stage in summary["progress"]]
		self.assertIn("Pay at pickup", labels)
		self.assertEqual(len(summary["progress"]), 4)

	def test_delivery_order_keeps_shipping_when_a_rate_is_configured(self):
		from frappe.utils import flt

		from shop.storefront import cart as cart_module

		if not flt(frappe.db.get_single_value("Shop Settings", "flat_shipping_rate")):
			self.skipTest("no flat shipping rate configured on this site")
		# Whichever delivery method the store currently allows: advance and cod
		# both take the courier path, pickup is the only one that waives it.
		settings = frappe.get_doc("Shop Settings")
		method = None
		if settings.enable_advance_payment:
			method = "advance"
		elif settings.enable_cod:
			allowed = checkout.cod_cities(settings)
			if not allowed or ADDRESS["city"].lower() in allowed:
				method = "cod"
		if not method:
			self.skipTest("no delivery payment method is currently enabled")
		self._set_pickup(True)
		cart.add_item("SHOP-DEMO-003")
		payload = cart_module.cart_payload(cart_module.resolve_cart())
		if not payload.get("shipping"):
			self.skipTest("shipping is free for this cart under current settings")
		result = checkout.place_order(customer=BUYER, address=ADDRESS, payment_method=method)
		sales_order = frappe.get_doc("Sales Order", result["sales_order"])
		shipping_rows = [tax for tax in sales_order.taxes if (tax.description or "").lower() == "shipping"]
		self.assertTrue(shipping_rows)

	def test_settings_round_trip(self):
		updated = settings_api.save_settings({"enable_pickup": 1})
		self.assertEqual(int(updated["enable_pickup"]), 1)
		saved = settings_api.save_pickup_locations(
			[
				{
					"location_name": "Branch",
					"address": "2 Mall Road, Lahore",
					"latitude": "31.4180",
					"longitude": "73.0822",
					"phone": "03011111111",
				}
			]
		)
		self.assertEqual(len(saved["pickup_locations"]), 1)
		self.assertEqual(saved["pickup_locations"][0]["location_name"], "Branch")
		# Rows without a name or address are ignored rather than stored broken.
		saved = settings_api.save_pickup_locations([{"location_name": "", "address": ""}])
		self.assertEqual(saved["pickup_locations"], [])

	def test_map_provider_switches_between_osm_and_google(self):
		self._set_pickup(True)
		frappe.db.set_single_value("Shop Settings", "map_embed_provider", "OpenStreetMap")
		frappe.get_cached_doc("Shop Settings")
		row = checkout.get_checkout_summary()["pickup_locations"][0]
		self.assertIn("openstreetmap.org/export/embed.html", row["map_url"])

		updated = settings_api.save_settings({"map_embed_provider": "Google Maps"})
		self.assertEqual(updated["map_embed_provider"], "Google Maps")
		row = checkout.get_checkout_summary()["pickup_locations"][0]
		self.assertIn("maps.google.com", row["map_url"])
		self.assertIn("output=embed", row["map_url"])
		# The directions link stays Google either way — storefront.js swaps it
		# to Apple Maps on iPhones at the page level.
		self.assertIn("google.com/maps/dir", row["directions_url"])

		# Unknown providers fall back to the default embed rather than breaking.
		updated = settings_api.save_settings({"map_embed_provider": "Bing"})
		self.assertEqual(updated["map_embed_provider"], "OpenStreetMap")

	def test_pickup_orders_are_never_sent_for_shipping(self):
		from shop.fulfillment import service

		self._set_pickup(True)
		cart.add_item("SHOP-DEMO-003")
		result = checkout.place_order(
			customer=BUYER, address=ADDRESS, payment_method="pickup", pickup_location=LOCATION["location_name"]
		)
		order = result["sales_order"]
		# Manual hand-off is refused with a pickup-specific message...
		with self.assertRaises(frappe.ValidationError) as caught:
			service.send(order, "manual")
		self.assertIn("collected in person", str(caught.exception))
		# ...and the automatic route skips the order without logging an error.
		previous_auto = frappe.db.get_single_value("Shop Settings", "auto_send_to_fulfillment")
		frappe.db.set_single_value("Shop Settings", "auto_send_to_fulfillment", 1)
		frappe.get_cached_doc("Shop Settings")
		self.addCleanup(
			frappe.db.set_single_value, "Shop Settings", "auto_send_to_fulfillment", previous_auto
		)
		service.auto_send(order)
		self.assertFalse(frappe.db.exists("Shop Fulfillment", {"sales_order": order}))
		# The admin order view reports pickup instead of a shipping state.
		from shop.api import orders as orders_api

		detail = orders_api.get_order(order)
		self.assertEqual(detail["pickup_location"], LOCATION["location_name"])
		self.assertEqual(detail["fulfillment_status"], "Awaiting pickup")


def orders_summary(sales_order) -> dict:
	from shop.storefront import orders

	return orders.order_summary(sales_order)
