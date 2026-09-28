"""Regression tests for the fraud scoring model.

Pure functions only: no site, no database, no fixtures. The point is to pin
the decisions that were wrong before - a 60-minute velocity cliff, an
attacker-controlled address owning two thirds of the score, noise signals
weighted like evidence, and a verdict ladder that ignored the score - so a
later change cannot quietly reintroduce them.
"""

import unittest


class TestIdentityHelpers(unittest.TestCase):
	def test_normalize_phone_strips_formatting(self):
		from shop.integrations.fraud import normalize_phone

		self.assertEqual(normalize_phone("+92 300-1234567"), "3001234567")
		self.assertEqual(normalize_phone("0300-1234567"), "3001234567")
		self.assertEqual(normalize_phone(None), "")

	def test_normalize_city_is_one_key_per_place(self):
		from shop.integrations.fraud import normalize_city

		self.assertEqual(normalize_city("  Rahim   Yar Khan "), "rahim yar khan")
		self.assertEqual(normalize_city("RAHIM YAR KHAN"), "rahim yar khan")
		self.assertEqual(normalize_city(None), "")


class TestVelocityDecay(unittest.TestCase):
	def test_recent_order_counts_full_and_old_orders_fade(self):
		from shop.integrations.fraud import VELOCITY_HALF_LIFE_HOURS, decay_factor

		self.assertEqual(decay_factor(0), 1.0)
		self.assertAlmostEqual(decay_factor(VELOCITY_HALF_LIFE_HOURS), 0.5, places=5)
		self.assertAlmostEqual(decay_factor(VELOCITY_HALF_LIFE_HOURS * 2), 0.25, places=5)
		# An order from 23 hours ago must still count for something: the whole
		# point of the day window is that waiting an hour is not a free reset.
		self.assertGreater(decay_factor(23), 0.05)

	def test_velocity_window_covers_a_whole_day(self):
		from shop.integrations.fraud import VELOCITY_WINDOW_HOURS

		self.assertGreaterEqual(VELOCITY_WINDOW_HOURS, 24)


class TestAddressContributionIsCapped(unittest.TestCase):
	def test_address_cannot_own_the_score(self):
		from shop.integrations.fraud import ADDRESS_SCORE_CAP

		self.assertLessEqual(ADDRESS_SCORE_CAP, 40)

	def test_no_negative_weights(self):
		"""Bonuses for a "nice" address used to mask real risk."""
		from shop.integrations.signal_weights import DEFAULT_SIGNAL_WEIGHTS

		negative = {k: v for k, v in DEFAULT_SIGNAL_WEIGHTS.items() if v < 0}
		self.assertEqual(negative, {})

	def test_noise_signals_are_recorded_but_cheap(self):
		from shop.integrations.signal_weights import DEFAULT_SIGNAL_WEIGHTS as W

		self.assertLessEqual(W["missing_fingerprint"], 5)
		self.assertEqual(W["incognito_privacy"], 0)
		self.assertEqual(W["fp_rare_device"], 0)


class TestVerdictLadder(unittest.TestCase):
	class _Settings(dict):
		def get(self, key, default=None):
			return dict.get(self, key, default)

		def __getattr__(self, key):
			try:
				return self[key]
			except KeyError:
				return None

	SETTINGS = _Settings(
		{
			"fraud_advance_threshold": 70,
			"fraud_blacklist_blocks_all": 0,
		}
	)

	def test_high_score_alone_never_blocks(self):
		from shop.integrations.fraud import _verdict

		# It still escalates a collecting order (advance threshold), but only
		# verified evidence may turn a score into a refusal.
		self.assertEqual(_verdict(95, {}, None, self.SETTINGS, "cod"), "Advance Required")
		self.assertEqual(_verdict(95, {}, None, self.SETTINGS, "raast"), "Flag")

	def test_high_score_with_verified_evidence_blocks_collecting_orders(self):
		from shop.integrations.fraud import _verdict

		self.assertEqual(
			_verdict(95, {}, None, self.SETTINGS, "cod", verified_evidence=True), "Block"
		)
		# Prepaid is already paid: the engine informs, it does not gate.
		self.assertEqual(
			_verdict(95, {}, None, self.SETTINGS, "raast", verified_evidence=True), "Flag"
		)

	def test_blacklist_and_velocity_still_block_cod(self):
		from shop.integrations.fraud import _verdict

		self.assertEqual(_verdict(10, {}, {"name": "BL-1"}, self.SETTINGS, "cod"), "Block")
		self.assertEqual(
			_verdict(10, {"velocity_block": True}, None, self.SETTINGS, "pickup"), "Block"
		)
		# ... and a prepaid order passes through the blacklist unharmed.
		self.assertEqual(_verdict(10, {}, {"name": "BL-1"}, self.SETTINGS, "raast"), "Pass")

	def test_flag_marks_the_order_for_review(self):
		from shop.integrations.fraud import _verdict

		signals = {}
		self.assertEqual(_verdict(45, signals, None, self.SETTINGS, "cod"), "Flag")
		self.assertTrue(signals.get("requires_manual_review"))

	def test_advance_threshold_is_configurable(self):
		from shop.integrations.fraud import _verdict

		loose = self._Settings({**self.SETTINGS, "fraud_advance_threshold": 50})
		self.assertEqual(_verdict(55, {}, None, loose, "cod"), "Advance Required")

	def test_flag_threshold_is_configurable_once_the_field_exists(self):
		from shop.integrations.fraud import _verdict

		strict = self._Settings({**self.SETTINGS, "fraud_flag_threshold": 20})
		self.assertEqual(_verdict(25, {}, None, strict, "raast"), "Flag")
		self.assertEqual(_verdict(15, {}, None, strict, "raast"), "Pass")

	def test_flag_line_and_advance_line_are_different_questions(self):
		"""Flag asks a human to look; Advance asks the customer for money."""
		from shop.integrations.fraud import _verdict

		# 40-69: internal review only, and free of charge to the customer.
		self.assertEqual(_verdict(45, {}, None, self.SETTINGS, "cod"), "Flag")
		# 70+: the customer is switched to paying an advance up front.
		self.assertEqual(_verdict(75, {}, None, self.SETTINGS, "cod"), "Advance Required")
		# Moving the flag line must not drag the advance line with it.
		loose = self._Settings({**self.SETTINGS, "fraud_flag_threshold": 20})
		self.assertEqual(_verdict(75, {}, None, loose, "cod"), "Advance Required")


class TestSettingsKnobsExist(unittest.TestCase):
	"""The code reads these fields, so they have to actually be in the doctype."""

	def _settings_fields(self):
		import json
		import os

		# Look for the doctype at each level, and one level down inside the
		# nested module directory this app uses - a test should not have to
		# know which shape the app was laid out in.
		here = os.path.dirname(os.path.abspath(__file__))
		candidate = None
		for _ in range(6):
			for prefix in (here, os.path.join(here, "shop")):
				attempt = os.path.join(prefix, "doctype", "shop_settings", "shop_settings.json")
				if os.path.isfile(attempt):
					candidate = attempt
					break
			if candidate:
				break
			here = os.path.dirname(here)
		if not candidate:  # pragma: no cover - only if the doctype is moved
			self.fail("shop_settings.json not found near " + os.path.dirname(os.path.abspath(__file__)))
		with open(candidate) as handle:
			doc = json.load(handle)
		return {field.get("fieldname"): field for field in doc.get("fields", [])}

	def test_review_flag_score_is_a_real_setting(self):
		fields = self._settings_fields()
		self.assertIn("fraud_flag_threshold", fields)
		self.assertEqual(fields["fraud_flag_threshold"]["fieldtype"], "Int")
		self.assertEqual(str(fields["fraud_flag_threshold"]["default"]), "40")

	def test_velocity_setting_does_not_still_claim_to_be_hourly(self):
		fields = self._settings_fields()
		label = (fields["fraud_velocity_max"]["label"] or "").lower()
		self.assertNotIn("hour", label)

	def test_flag_default_sits_below_the_advance_default(self):
		fields = self._settings_fields()
		self.assertLess(
			int(fields["fraud_flag_threshold"]["default"]),
			int(fields["fraud_advance_threshold"]["default"]),
		)


class TestScoringModelIsSingleSourced(unittest.TestCase):
	def test_both_passes_call_the_same_model(self):
		import inspect

		from shop.integrations.fraud import evaluate_risk, fast_risk

		for fn in (fast_risk, evaluate_risk):
			with self.subTest(fn=fn.__name__):
				self.assertIn("_score_order", inspect.getsource(fn))
				self.assertIn("_verdict", inspect.getsource(fn))

	def test_model_never_reads_a_missing_signal_as_clean(self):
		"""Absent inputs must be absent, not zero-with-a-good-meaning."""
		import inspect

		from shop.integrations.fraud import _score_order

		source = inspect.getsource(_score_order)
		self.assertIn('ip_intel_unavailable', source)
		self.assertIn("identity_unverified", source)


if __name__ == "__main__":
	unittest.main()
