"""Shared fixtures for the shop test suite."""

import frappe


def force_cod_enabled(test) -> None:
	"""Enable COD with an open city list for the test, then restore the store.

	These tests exercise checkout mechanics by placing cash orders, but
	whether COD is offered is the merchant's live decision (they may have it
	switched off, or restricted to certain cities). Snapshot their switch,
	turn COD on for the run, and put back whatever was there afterwards.
	"""
	previous = (
		frappe.db.get_single_value("Shop Settings", "enable_cod"),
		frappe.db.get_single_value("Shop Settings", "cod_allowed_cities"),
	)
	frappe.db.set_single_value("Shop Settings", "enable_cod", 1)
	frappe.db.set_single_value("Shop Settings", "cod_allowed_cities", "")
	frappe.get_cached_doc("Shop Settings")
	test.addCleanup(restore_cod, previous)


def restore_cod(previous) -> None:
	frappe.db.set_single_value("Shop Settings", "enable_cod", previous[0])
	frappe.db.set_single_value("Shop Settings", "cod_allowed_cities", previous[1] or "")
	frappe.get_cached_doc("Shop Settings")
