import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from shop.storefront import cart, checkout

BUYER = {"email": "advance@example.com", "full_name": "Adv Ance", "phone": "9999901111"}
ADDRESS = {"address_line1": "7 Advance Rd", "city": "Bengaluru", "country": "India", "pincode": "560004", "landmark": "Gate 7"}

SETTING_FIELDS = (
	"enable_advance_payment",
	"advance_payment_mode",
	"advance_payment_percent",
	"advance_payment_flat",
	"raast_payment_instructions",
	"enable_raast_qr",
	"raast_iban",
	"raast_account_title",
	"raast_bank_name",
	"enable_fraud_check",
	"enable_cod",
	"cod_allowed_cities",
	"auto_send_to_fulfillment",
	"fulfillment_provider",
	"auto_bill_on_payment",
	"landmark_required",
	"payment_gateway_account",
)


class TestAdvancePayment(IntegrationTestCase):
	def setUp(self):
		frappe.db.delete("Shop Cart")
		if hasattr(frappe.local, "request"):
			del frappe.local.request
		self._snapshot = {
			field: frappe.db.get_single_value("Shop Settings", field) for field in SETTING_FIELDS
		}
		self.configure_advance(percent=20)

	def tearDown(self):
		for field, value in self._snapshot.items():
			frappe.db.set_single_value("Shop Settings", field, value)
		frappe.get_cached_doc("Shop Settings")

	def configure_advance(self, percent=20, mode="Percent", flat=0, instructions="", enabled=1):
		frappe.db.set_single_value(
			"Shop Settings",
			{
				"enable_advance_payment": enabled,
				"advance_payment_mode": mode,
				"advance_payment_percent": percent,
				"advance_payment_flat": flat,
				"raast_payment_instructions": instructions,
				# Advance and Raast QR are one option, so pin the QR side
				# here instead of inheriting whatever the site has on.
				"enable_raast_qr": 1,
				"raast_iban": "PK61MEZN0012030105593061",
				"raast_account_title": "Adv Ance",
				# deterministic checkout: no fraud calls, no surprise shipping
				"enable_fraud_check": 0,
				"auto_send_to_fulfillment": 0,
			},
		)
		frappe.get_cached_doc("Shop Settings")

	def test_settings_api_round_trip(self):
		"""The admin panel persists advance fields through save_settings."""
		from shop.api import settings as settings_api

		updated = settings_api.save_settings(
			{
				"enable_advance_payment": 1,
				"advance_payment_mode": "Flat",
				"advance_payment_flat": 250,
				"advance_payment_percent": 35,
				"raast_payment_instructions": "Test account 0000",
				"cod_allowed_cities": "Rahimyarkhan",
			}
		)
		self.assertEqual(updated["enable_advance_payment"], 1)
		self.assertEqual(updated["advance_payment_mode"], "Flat")
		self.assertEqual(flt(updated["advance_payment_flat"]), 250.0)
		self.assertEqual(updated["advance_payment_percent"], 35)
		self.assertEqual(updated["raast_payment_instructions"], "Test account 0000")
		self.assertEqual(updated["cod_allowed_cities"], "Rahimyarkhan")
		# Unknown basis values fall back to Percent instead of persisting.
		reverted = settings_api.save_settings({"advance_payment_mode": "Bogus"})
		self.assertEqual(reverted["advance_payment_mode"], "Percent")

	def methods(self):
		summary = checkout.get_checkout_summary()
		return summary, {row["method"]: row for row in summary["payment_methods"]}

	# ---------- checkout option ----------

	def test_summary_hides_advance_when_disabled(self):
		self.configure_advance(enabled=0)
		cart.add_item("SHOP-DEMO-003")
		_, methods = self.methods()
		self.assertNotIn("advance", methods)

	def test_summary_shows_percent_advance_in_the_merged_option(self):
		cart.add_item("SHOP-DEMO-003")
		summary, methods = self.methods()
		# Advance and Raast QR are one row: same split, same promise.
		self.assertIn("raast", methods)
		self.assertNotIn("advance", methods)
		total = summary["cart"]["total"]
		self.assertGreater(total, 0)
		self.assertAlmostEqual(methods["raast"]["advance_amount"], total * 0.20, places=2)
		self.assertAlmostEqual(methods["raast"]["balance_amount"], total * 0.80, places=2)
		self.assertIn("on delivery", methods["raast"]["label"])

	def test_summary_flat_amount_clamped_to_total(self):
		self.configure_advance(mode="Flat", flat=999999)
		cart.add_item("SHOP-DEMO-003")
		summary, methods = self.methods()
		self.assertEqual(methods["raast"]["advance_amount"], summary["cart"]["total"])
		self.assertEqual(methods["raast"]["balance_amount"], 0)
		self.assertIn("full", methods["raast"]["label"].lower())

	def test_place_order_rejects_disabled_advance(self):
		self.configure_advance(enabled=0)
		cart.add_item("SHOP-DEMO-003")
		with self.assertRaises(frappe.ValidationError):
			checkout.place_order(customer=BUYER, address=ADDRESS, payment_method="advance")

	# ---------- placement ----------

	def test_place_order_stamps_advance_fields(self):
		self.configure_advance(instructions="Meezan Bank 0000-0000-0000 (Adv Ance)")
		cart.add_item("SHOP-DEMO-003")
		result = checkout.place_order(customer=BUYER, address=ADDRESS, payment_method="advance")
		self.assertFalse(result.get("payment_url"))
		order = frappe.get_doc("Sales Order", result["sales_order"])
		self.assertEqual(order.custom_payment_method, "advance")
		self.assertGreater(flt(order.custom_advance_amount), 0)
		# confirmation page carries the advance block + account instructions
		from shop.storefront import orders as store_orders

		token = frappe.db.get_value("Shop Cart", {"sales_order": order.name}, "token")
		page = store_orders.get_order_summary(order.name, token)
		self.assertTrue(page["advance_payment"])
		self.assertIn("Meezan", page["advance_payment"]["instructions"])
		self.assertAlmostEqual(
			page["advance_payment"]["balance"],
			flt(order.grand_total) - flt(order.custom_advance_amount),
			places=2,
		)
		self.assertEqual(page["payment_method"], "advance")

	# ---------- recording + settlement ----------

	def test_mark_advance_received_then_balance_settles(self):
		from shop.api import orders as orders_api
		from shop.storefront import orders as store_orders

		cart.add_item("SHOP-DEMO-003")
		result = checkout.place_order(customer=BUYER, address=ADDRESS, payment_method="advance")
		name = result["sales_order"]

		payload = orders_api.mark_advance_received(name, reference_no="TRX-ADV-1")
		self.assertEqual(payload["payment_status"], "Advance Received")
		self.assertAlmostEqual(payload["payment_received"], payload["advance_amount"], places=2)
		self.assertGreater(payload["payment_balance"], 0)
		self.assertEqual(payload["payment_method"], "advance")

		# confirmation page flips to "advance received"
		token = frappe.db.get_value("Shop Cart", {"sales_order": name}, "token")
		page = store_orders.get_order_summary(name, token)
		self.assertIn("Advance received", page["advance_payment"]["line"])
		labels = [stage["label"] for stage in page["progress"]]
		self.assertEqual(labels[1], "Advance paid")
		self.assertEqual(page["progress"][1]["done"], "true")

		# balance settles through the usual Mark paid, then the guard kicks in
		payload = orders_api.mark_paid(name)
		self.assertEqual(payload["payment_status"], "Paid")
		self.assertAlmostEqual(payload["payment_balance"], 0.0, places=2)
		with self.assertRaises(frappe.ValidationError):
			orders_api.mark_paid(name)
		with self.assertRaises(frappe.ValidationError):
			orders_api.mark_advance_received(name)

	def test_admin_list_and_filter_reflect_advance(self):
		from shop.api import orders as orders_api

		cart.add_item("SHOP-DEMO-003")
		result = checkout.place_order(customer=BUYER, address=ADDRESS, payment_method="advance")
		name = result["sales_order"]
		orders_api.mark_advance_received(name)

		detail = orders_api.get_order(name)
		self.assertEqual(detail["payment_status"], "Advance Received")
		self.assertGreater(detail["payment_balance"], 0)
		self.assertTrue(detail["formatted_payment_balance"])

		page = orders_api.get_orders(payment="Advance Received")
		self.assertIn(name, [row["name"] for row in page["orders"]])
		row = next(row for row in page["orders"] if row["name"] == name)
		self.assertEqual(row["payment_status"], "Advance Received")
		self.assertGreater(row["payment_balance"], 0)

	def test_advance_ships_itself_when_the_store_asks(self):
		from shop.api import orders as orders_api
		from shop.fulfillment import service

		frappe.db.set_single_value(
			"Shop Settings", {"auto_send_to_fulfillment": 1, "fulfillment_provider": "manual"}
		)
		frappe.clear_cache(doctype="Shop Settings")
		cart.add_item("SHOP-DEMO-003")
		result = checkout.place_order(customer=BUYER, address=ADDRESS, payment_method="advance")
		name = result["sales_order"]
		orders_api.mark_advance_received(name)
		record = service.for_order(name)
		self.assertIsNotNone(record)
		self.assertEqual(record["status"], "Accepted")

	# ---------- settings validation ----------

	def test_percent_bounds_enforced(self):
		settings = frappe.get_doc("Shop Settings")
		settings.enable_advance_payment = 1
		settings.advance_payment_mode = "Percent"
		settings.advance_payment_percent = 0
		self.assertRaises(frappe.ValidationError, settings.validate)
		settings.advance_payment_percent = 101
		self.assertRaises(frappe.ValidationError, settings.validate)
		settings.advance_payment_percent = 20
		settings.advance_payment_flat = -5
		settings.advance_payment_mode = "Flat"
		self.assertRaises(frappe.ValidationError, settings.validate)
		settings.advance_payment_flat = 500
		settings.validate()
