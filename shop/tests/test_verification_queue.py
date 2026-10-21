"""Which addresses the verification queue still has work for.

The queue is for the addresses neither geocoder could place. An address that
was processed - by ORS or by GMS - is located and has nothing left to prove,
so it leaves the queue and does not come back when the freshness window
passes. A record the merchant queued by hand always comes back.

These are pure functions: no site, no database, no fixtures.
"""

import unittest


class TestQueueNeedsWork(unittest.TestCase):
	def _row(self, **overrides):
		import frappe

		row = {
			"status": None,
			"ors_status": "Skipped",
			"gms_status": "Disabled",
			"last_verified_on": None,
		}
		row.update(overrides)
		return frappe._dict(row)

	def _needs_work(self, row, gms_enabled=True, ors_enabled=True):
		from shop.integrations.verification import _needs_work

		return _needs_work(row, gms_enabled, ors_enabled)

	def test_an_address_that_has_not_been_tried_needs_work(self):
		self.assertTrue(self._needs_work(self._row()))

	def test_an_address_placed_by_ors_leaves_the_queue(self):
		self.assertFalse(self._needs_work(self._row(ors_status="Complete")))

	def test_an_address_placed_by_gms_leaves_the_queue(self):
		self.assertFalse(self._needs_work(self._row(gms_status="Complete")))

	def test_an_address_both_providers_failed_stays_in_the_queue(self):
		self.assertTrue(
			self._needs_work(self._row(ors_status="Failed", gms_status="Failed"))
		)

	def test_a_placed_address_does_not_come_back_when_it_goes_stale(self):
		# The freshness window used to put every address back on the list.
		# A placement is the answer; how old it is does not change that.
		from datetime import datetime, timedelta

		old = datetime.now() - timedelta(days=365)
		self.assertFalse(self._needs_work(self._row(ors_status="Complete", last_verified_on=old)))

	def test_a_record_queued_by_hand_always_comes_back(self):
		self.assertTrue(self._needs_work(self._row(status="Queued", ors_status="Complete")))

	def test_nothing_is_counted_when_both_providers_are_off(self):
		self.assertFalse(self._needs_work(self._row(), gms_enabled=False, ors_enabled=False))

	def test_a_provider_that_is_off_is_not_waited_for(self):
		# GMS off means GMS has nothing to say, so ORS alone decides.
		self.assertFalse(
			self._needs_work(self._row(ors_status="Complete", gms_status="Disabled"), gms_enabled=False)
		)
