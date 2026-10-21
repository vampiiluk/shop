"""A hand-placed order lands in the same place as a site order.

A shop takes orders over the phone, on WhatsApp and at the counter. Those
orders have to arrive as the same kind of order the site takes: the same
Sales Order, the same customer, the same fulfilment, the same invoice.

These tests place one and take it back off the books afterwards, so the
shop is not left with a stray order.
"""

import frappe
from frappe.tests import IntegrationTestCase

from shop.api import manual_orders
from shop.tests import force_cod_enabled

CUSTOMER = {
	"full_name": "Manual Order Test",
	"email": "manual-order-test@example.com",
	"phone": "03001234567",
}
ADDRESS = {
	"address_line1": "12 Test Street",
	"address_line2": "Flat 3",
	"city": "Lahore",
	"state": "Punjab",
	"country": "Pakistan",
	"pincode": "54000",
	"landmark": "Opposite the test bank",
	"alt_phone": "03007654321",
}


class TestManualOrders(IntegrationTestCase):
	def setUp(self):
		force_cod_enabled(self)
		self.addCleanup(self._remove_test_records)

	def _remove_test_records(self):
		"""Take the order, and the records it made, back off the books."""
		for row in frappe.get_all(
			"Sales Order", filters={"contact_email": CUSTOMER["email"]}, pluck="name"
		):
			order = frappe.get_doc("Sales Order", row)
			addresses = {order.shipping_address_name, order.customer_address}
			customer = order.customer
			contacts = frappe.get_all(
				"Dynamic Link",
				filters={"link_doctype": "Customer", "link_name": customer},
				pluck="parent",
			)
			frappe.db.set_value("Sales Order", row, "docstatus", 2, update_modified=False)
			frappe.db.commit()
			frappe.delete_doc("Sales Order", row, force=True, ignore_permissions=True)
			# The cart carries the guest's secret for the receipt link, so it
			# goes with the order.
			for cart in frappe.get_all("Shop Cart", filters={"sales_order": row}, pluck="name"):
				frappe.delete_doc("Shop Cart", cart, force=True, ignore_permissions=True)
			for address in addresses:
				if address and frappe.db.exists("Address", address):
					frappe.delete_doc("Address", address, force=True, ignore_permissions=True)
			for contact in contacts:
				if frappe.db.exists("Contact", contact):
					frappe.delete_doc("Contact", contact, force=True, ignore_permissions=True)
			if frappe.db.exists("Customer", customer):
				frappe.delete_doc("Customer", customer, force=True, ignore_permissions=True)
		frappe.db.commit()

	def _sellable_item(self) -> str:
		"""An item a customer may buy, whatever the catalogue happens to hold.

		The demo products are not published on every site, so the test
		finds one that is rather than naming one.
		"""
		from shop.storefront import stock

		for row in frappe.get_all(
			"Shop Product", filters={"published": 1, "has_variants": 0}, fields=["item"], limit=50
		):
			if not frappe.db.get_value("Item", row.item, "disabled"):
				return row.item
		self.skipTest("this site has no published product to order")

	def _place(self, **overrides):
		payload = {
			"customer": dict(CUSTOMER),
			"address": dict(ADDRESS),
			"items": [{"item_code": self._sellable_item(), "qty": 2, "rate": 1500}],
			"payment_method": "cod",
			"notes": "Placed by hand over the phone.",
			"send_email": False,
		}
		payload.update(overrides)
		return manual_orders.create(payload)

	def test_the_order_is_a_real_sales_order(self):
		result = self._place()
		order = frappe.get_doc("Sales Order", result["order"])
		self.assertEqual(order.docstatus, 1)
		self.assertEqual(order.get("custom_manual_order"), 1)
		self.assertEqual(order.get("custom_order_notes"), "Placed by hand over the phone.")
		self.assertEqual(order.get("custom_payment_method"), "cod")
		self.assertEqual(order.contact_email, CUSTOMER["email"])
		self.assertEqual(order.contact_phone, CUSTOMER["phone"])
		self.assertEqual(order.contact_mobile, CUSTOMER["phone"])
		self.assertEqual(len(order.items), 1)
		self.assertEqual(order.items[0].item_code, self._sellable_item())
		self.assertEqual(order.items[0].qty, 2)

	def test_the_customer_and_the_address_are_recorded(self):
		result = self._place()
		order = frappe.get_doc("Sales Order", result["order"])

		address = frappe.get_doc("Address", order.shipping_address_name)
		self.assertEqual(address.address_line1, ADDRESS["address_line1"])
		self.assertEqual(address.address_line2, ADDRESS["address_line2"])
		self.assertEqual(address.city, ADDRESS["city"])
		self.assertEqual(address.pincode, ADDRESS["pincode"])
		self.assertEqual(address.get("custom_landmark"), ADDRESS["landmark"])
		self.assertEqual(address.get("custom_alt_phone"), ADDRESS["alt_phone"])
		self.assertEqual(address.email_id, CUSTOMER["email"])
		self.assertEqual(address.phone, CUSTOMER["phone"])

		customer = frappe.get_doc("Customer", order.customer)
		self.assertEqual(customer.customer_name, CUSTOMER["full_name"])

	def test_the_order_lands_in_the_desk_list(self):
		from shop.api.orders import get_orders

		result = self._place()
		listed = get_orders(search=result["order"])
		self.assertIn(result["order"], [row["name"] for row in listed["orders"]])

	def test_the_guest_receipt_link_carries_a_secret(self):
		from shop.storefront.orders import can_view

		result = self._place()
		order = frappe.get_doc("Sales Order", result["order"])
		cart = frappe.get_all("Shop Cart", filters={"sales_order": order.name}, pluck="token")
		self.assertTrue(cart, "the order needs a cart to carry the guest's secret")
		self.assertTrue(can_view(order.name, cart[0]))

	def test_a_missing_name_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self._place(customer={"full_name": "", "email": CUSTOMER["email"], "phone": CUSTOMER["phone"]})

	def test_a_missing_email_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self._place(customer={"full_name": CUSTOMER["full_name"], "email": "", "phone": CUSTOMER["phone"]})

	def test_a_missing_phone_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self._place(customer={"full_name": CUSTOMER["full_name"], "email": CUSTOMER["email"], "phone": ""})

	def test_a_missing_address_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self._place(address={**ADDRESS, "address_line1": ""})

	def test_an_order_with_no_items_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self._place(items=[])

	def test_cod_outside_its_cities_is_refused(self):
		previous = frappe.db.get_single_value("Shop Settings", "cod_allowed_cities")
		frappe.db.set_single_value("Shop Settings", "cod_allowed_cities", "karachi")
		frappe.get_cached_doc("Shop Settings")
		self.addCleanup(self._restore_cod_cities, previous)
		with self.assertRaises(frappe.ValidationError):
			self._place()

	def _restore_cod_cities(self, previous):
		frappe.db.set_single_value("Shop Settings", "cod_allowed_cities", previous or "")
		frappe.get_cached_doc("Shop Settings")

	def test_the_landmark_is_required_when_the_shop_asks_for_it(self):
		previous = frappe.db.get_single_value("Shop Settings", "landmark_required")
		frappe.db.set_single_value("Shop Settings", "landmark_required", 1)
		frappe.get_cached_doc("Shop Settings")
		self.addCleanup(self._restore_landmark, previous)
		with self.assertRaises(frappe.ValidationError):
			self._place(address={**ADDRESS, "landmark": ""})

	def _restore_landmark(self, previous):
		frappe.db.set_single_value("Shop Settings", "landmark_required", previous)
		frappe.get_cached_doc("Shop Settings")

	def _coupon(self, percentage=10, code="MANUALORDER10"):
		"""A coupon of the test's own, so the shop's real ones are untouched."""
		settings = frappe.get_cached_doc("Shop Settings")
		company = settings.company
		currency = settings.currency or frappe.get_cached_value(
			"Company", company, "default_currency"
		)
		rule = frappe.get_doc(
			{
				"doctype": "Pricing Rule",
				"title": "Manual order test rule",
				"apply_on": "Transaction",
				"price_or_product_discount": "Price",
				"selling": 1,
				"coupon_code_based": 1,
				"company": company,
				"currency": currency,
				"apply_discount_on": "Grand Total",
				"rate_or_discount": "Discount Percentage",
				"discount_percentage": percentage,
				"discount_amount": 0,
				"disable": 0,
			}
		).insert(ignore_permissions=True)
		coupon = frappe.get_doc(
			{
				"doctype": "Coupon Code",
				"coupon_name": "Manual order test coupon",
				"coupon_type": "Promotional",
				"coupon_code": code,
				"pricing_rule": rule.name,
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()
		self.addCleanup(self._remove_coupon, coupon.name, rule.name)
		return coupon

	def _remove_coupon(self, coupon, rule):
		if frappe.db.exists("Coupon Code", coupon):
			frappe.delete_doc("Coupon Code", coupon, force=True, ignore_permissions=True)
		if frappe.db.exists("Pricing Rule", rule):
			frappe.delete_doc("Pricing Rule", rule, force=True, ignore_permissions=True)
		frappe.db.commit()

	def test_the_coupon_takes_the_discount_off_the_order(self):
		coupon = self._coupon()
		discounted = frappe.get_doc("Sales Order", self._place(coupon_code=coupon.coupon_code)["order"])
		plain = frappe.get_doc("Sales Order", self._place()["order"])

		self.assertEqual(discounted.total, plain.total)
		self.assertEqual(discounted.discount_amount, 300)
		self.assertEqual(discounted.apply_discount_on, "Grand Total")
		self.assertEqual(discounted.grand_total, plain.grand_total - 300)

	def test_the_coupon_is_written_down_on_the_order(self):
		coupon = self._coupon()
		order = frappe.get_doc("Sales Order", self._place(coupon_code=coupon.coupon_code)["order"])
		self.assertEqual(order.get("custom_coupon_code"), coupon.coupon_code)

	def test_the_coupon_is_counted_as_used_once(self):
		coupon = self._coupon()
		self._place(coupon_code=coupon.coupon_code)
		self.assertEqual(frappe.db.get_value("Coupon Code", coupon.name, "used"), 1)

	def test_a_coupon_that_does_not_exist_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self._place(coupon_code="NOSUCHCOUPONCODE")
		self.assertFalse(
			frappe.get_all("Sales Order", filters={"contact_email": CUSTOMER["email"]}),
			"a refused coupon must not leave an order behind",
		)

	def test_looking_a_coupon_up_does_not_use_it_up(self):
		coupon = self._coupon()
		checked = manual_orders.check_coupon(coupon.coupon_code, 3000)
		self.assertEqual(checked["valid"], 1)
		self.assertEqual(checked["discount"], 300)
		self.assertEqual(
			frappe.db.get_value("Coupon Code", coupon.name, "used"),
			0,
			"checking a coupon must not count as using it",
		)

	def test_looking_up_a_coupon_that_does_not_exist_says_so(self):
		checked = manual_orders.check_coupon("NOSUCHCOUPONCODE", 3000)
		self.assertEqual(checked["valid"], 0)
		self.assertTrue(checked["message"], "the merchant should be told why")
