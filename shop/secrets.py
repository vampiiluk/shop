"""Helpers for handling password fields on Shop Settings.

Frappe renders a stored password as a row of asterisks, and a client that
round-trips that masked value back to the server must not be allowed to store
it as though it were the real secret. The guard in ``save_settings`` used to
compare against a fixed six-asterisk mask, but the mask is as long as the real
value: a 198-character token comes back as 198 asterisks, slipped past the
check, and was written to the database. Three separate API keys were destroyed
that way, and the settings page still reported them as stored.

Matching on "is every character an asterisk" rather than on a length is the
whole fix, and it has to be used in both directions: on save, to refuse the
mask, and on read, so a value that is only asterisks is never mistaken for a
usable key.
"""

from __future__ import annotations


def is_mask(value: object) -> bool:
	"""True when ``value`` is a placeholder mask rather than a real secret.

	Frappe's mask is any run of asterisks. Treating any such run as "not
	provided" also covers the empty string, so callers need only this one check.
	"""
	if not value:
		return True
	text = str(value)
	return text.strip("*") == "" and "*" in text
