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

		# Nothing but the score: a review, never a refusal and never a demand
		# for money, because every point behind it was something the customer
		# typed.
		self.assertEqual(_verdict(95, {}, None, self.SETTINGS, "cod"), "Flag")
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

	def test_advance_payment_needs_something_the_server_looked_up(self):
		"""A deposit is a decision about a person, and most of the score is
		the person's own typing. That alone must not demand money."""
		from shop.integrations.fraud import _verdict

		typed_only = {
			"landmark_missing": True,
			"address_short_line1": True,
			"address_unknown_city": True,
			"risky_hour": True,
			"missing_fingerprint": True,
			"identity_unverified": True,
		}
		signals = dict(typed_only)
		self.assertEqual(_verdict(80, signals, None, self.SETTINGS, "cod"), "Flag")
		self.assertEqual(signals.get("advance_withheld_no_server_evidence"), 80)
		self.assertTrue(signals.get("requires_manual_review"))

	def test_advance_payment_fires_on_server_evidence(self):
		from shop.integrations.fraud import _verdict

		for evidence in (
			{"address_prior_failures": 3},
			{"address_activity_24h": {"orders_24h": 4, "customers_24h": 3}},
			{"repeat_history": {"total": 6, "failed": 3, "rto": 1}},
			{"fp_bot": "bad"},
			{"ip_intel": {"proxy": False, "is_tor": True, "abuse_score": 0}},
		):
			with self.subTest(evidence=evidence):
				self.assertEqual(_verdict(75, dict(evidence), None, self.SETTINGS, "cod"), "Advance Required")

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
		evidence = {"velocity_block": False, "address_prior_failures": 2}
		self.assertEqual(_verdict(55, dict(evidence), None, loose, "cod"), "Advance Required")
		self.assertEqual(_verdict(45, dict(evidence), None, loose, "cod"), "Flag")

	def test_flag_threshold_is_configurable_once_the_field_exists(self):
		from shop.integrations.fraud import _verdict

		strict = self._Settings({**self.SETTINGS, "fraud_flag_threshold": 20})
		self.assertEqual(_verdict(25, {}, None, strict, "raast"), "Flag")
		self.assertEqual(_verdict(15, {}, None, strict, "raast"), "Pass")

	def test_unset_flag_threshold_falls_back_to_40(self):
		from shop.integrations.fraud import _verdict

		unset = self._Settings(self.SETTINGS)
		self.assertEqual(_verdict(40, {}, None, unset, "raast"), "Flag")
		self.assertEqual(_verdict(39, {}, None, unset, "raast"), "Pass")

	def test_a_deliberate_zero_flag_threshold_is_honoured(self):
		"""Review every order is a legitimate choice, not a typo to overwrite."""
		from shop.integrations.fraud import _verdict

		paranoid = self._Settings({**self.SETTINGS, "fraud_flag_threshold": 0})
		self.assertEqual(_verdict(1, {}, None, paranoid, "raast"), "Flag")
		self.assertEqual(_verdict(0, {}, None, paranoid, "raast"), "Flag")

	def test_flag_line_and_advance_line_are_different_questions(self):
		"""Flag asks a human to look; Advance asks the customer for money."""
		from shop.integrations.fraud import _verdict

		evidence = {"address_prior_failures": 3}
		# 40-69: internal review only, and free of charge to the customer.
		self.assertEqual(_verdict(45, dict(evidence), None, self.SETTINGS, "cod"), "Flag")
		# 70+ with something the server found: the customer pays an advance.
		self.assertEqual(_verdict(75, dict(evidence), None, self.SETTINGS, "cod"), "Advance Required")
		# Moving the flag line must not drag the advance line with it.
		loose = self._Settings({**self.SETTINGS, "fraud_flag_threshold": 20})
		self.assertEqual(_verdict(75, dict(evidence), None, loose, "cod"), "Advance Required")

	def test_evidence_gate_does_not_gate_prepaid_orders(self):
		from shop.integrations.fraud import _verdict

		self.assertEqual(_verdict(90, {}, None, self.SETTINGS, "raast"), "Flag")


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


class TestBlacklistPhoneEquivalence(unittest.TestCase):
	"""Every spelling of a number must hit the same blacklist row.

	The stored side is written by a human in whatever format they type, so a
	comparison that only normalises the claim - as an earlier version did -
	silently stops matching "03001234567" and friends. That is the one control
	that can refuse an order, so it has to agree with normalize_phone().
	"""

	def test_variants_cover_the_prefix_spellings(self):
		from shop.integrations.fraud import _blacklist_phone_variants

		variants = _blacklist_phone_variants("3001234567")
		self.assertIn("3001234567", variants)
		self.assertIn("03001234567", variants)
		self.assertIn("923001234567", variants)

	def test_variants_are_the_same_whatever_spelling_arrives(self):
		"""The function normalises its own input, so a caller that forgets to
		normalise first cannot quietly match nothing."""
		from shop.integrations.fraud import _blacklist_phone_variants

		expected = ["03001234567", "3001234567", "923001234567"]
		for spelling in ("03001234567", "3001234567", "923001234567", "+92 (300) 123-4567"):
			with self.subTest(spelling=spelling):
				self.assertEqual(_blacklist_phone_variants(spelling), expected)

	def test_variants_of_nothing_are_empty(self):
		from shop.integrations.fraud import _blacklist_phone_variants

		self.assertEqual(_blacklist_phone_variants(""), [])
		self.assertEqual(_blacklist_phone_variants(None), [])

	def test_variants_ignore_formatting_in_the_claim(self):
		from shop.integrations.fraud import _blacklist_phone_variants, normalize_phone

		typed = normalize_phone("+92 (300) 123-4567")
		self.assertIn(typed, _blacklist_phone_variants(typed))

	def test_the_stored_side_is_normalised_in_sql(self):
		"""Guards the regression: a digits-only REPLACE, or a REPLACE of
		spaces and dashes, cannot match a stored number with a leading zero."""
		import inspect

		from shop.integrations.fraud import _BLACKLIST_PHONE_SQL

		self.assertIn("REGEXP_REPLACE", _BLACKLIST_PHONE_SQL)
		self.assertIn("[^0-9]", _BLACKLIST_PHONE_SQL)
		# and the query must compare against the variant list, not one spelling
		from shop.integrations.fraud import blacklist_hit

		self.assertIn("_blacklist_phone_variants", inspect.getsource(blacklist_hit))


class TestReviewReasons(unittest.TestCase):
	"""A reviewer needs to read why, not just how high."""

	def test_named_signals_become_sentences(self):
		from shop.api.fraud import _review_reasons

		reasons = _review_reasons(
			{
				"identity_unverified": True,
				"landmark_missing": True,
				"address_geo_not_found": "Address not found by geocoding",
				"city_rto_rate": 0.44,
			}
		)
		self.assertIn("Nothing about this order is proven yet", reasons)
		self.assertIn("No landmark given", reasons)
		self.assertIn("City return rate: 0.44", reasons)

	def test_false_and_empty_signals_are_not_reported(self):
		from shop.api.fraud import _review_reasons

		reasons = _review_reasons(
			{
				"identity_unverified": False,
				"landmark_missing": False,
				"fp_bot": False,
				"orders_last_24h": 0,
				"city_rto_rate": 0.0,
			}
		)
		self.assertEqual(reasons, [])

	def test_an_unmapped_signal_still_says_something(self):
		"""Never hand a reviewer a blank list for a flagged order."""
		from shop.api.fraud import _review_reasons

		reasons = _review_reasons({"some_signal_added_later": "yes"})
		self.assertTrue(reasons)
		self.assertIn("some_signal_added_later", reasons[0])

	def test_reason_list_is_bounded(self):
		from shop.api.fraud import _review_reasons

		blobby = {f"signal_{n}": True for n in range(40)}
		self.assertLessEqual(len(_review_reasons(blobby, limit=5)), 5)


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
