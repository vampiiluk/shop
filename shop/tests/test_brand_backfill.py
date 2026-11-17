from frappe.tests import IntegrationTestCase

from shop.patches.v9_brands.backfill_brands import match_brand


class TestBrandBackfill(IntegrationTestCase):
	def test_a_brand_at_the_start_of_the_name_is_matched(self):
		self.assertEqual(match_brand("Nike Flex Contact 3 'Bred'"), "Nike")
		self.assertEqual(match_brand("Adidas-D Rose 773 2020"), "Adidas")
		self.assertEqual(match_brand("The North Face Jester Backpack"), "The North Face")

	def test_short_names_are_boundary_checked(self):
		"""A prefix match must not turn an unrelated product into a branded one."""
		self.assertIsNone(match_brand("Niketo Runner"))
		self.assertEqual(match_brand("Clark Step Urban Mix"), "Clarks")
		self.assertEqual(match_brand("Clarks Slip On"), "Clarks")
		self.assertIsNone(match_brand("Daily Essential Clogs Blue"))

	def test_a_brand_that_shares_a_word_is_not_matched(self):
		self.assertEqual(match_brand("Lock & Lock Travel Mug"), "Lock & Lock")
		self.assertIsNone(match_brand("Lock Stars Figure"))

	def test_accents_and_curly_apostrophes_do_not_hide_a_brand(self):
		self.assertEqual(match_brand("VICTORIA’S SECRET ΤΣΑΝΤΑ Duffle Bag"), "Victoria's Secret")
		self.assertEqual(match_brand("Victoria's Secret Weekender"), "Victoria's Secret")

	def test_unbranded_products_stay_unbranded(self):
		for name in ("", "Bottle Red 500mL", "Travel Carry on Bag", "Oak Desk Organizer"):
			self.assertIsNone(match_brand(name))
