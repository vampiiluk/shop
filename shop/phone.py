"""Normalisation and validation for the WhatsApp business number.

The number is what customers tap to reach the shop, so it is worth getting right
in one place rather than at each use. It has to be stored in international form
with no punctuation, because that is the only form ``wa.me`` accepts: a local
``0303…`` number produces a link that silently fails to open a chat.

Normalisation is deliberately forgiving about how the number is typed — people
enter ``0303…``, ``+92 303…`` and ``92303…`` meaning the same thing — and strict
about what it stores.
"""

from __future__ import annotations

import re

# Countries this shop plausibly serves, so a local number can be promoted to
# international form. Matches the mapping used for pickup-location links.
DIAL_CODES = {
	"AE": "971", "AU": "61", "BD": "880", "CA": "1", "CN": "86", "GB": "44",
	"HK": "852", "ID": "62", "IN": "91", "IQ": "964", "IR": "98", "KE": "254",
	"KW": "965", "LK": "94", "MM": "95", "MY": "60", "NG": "234", "NP": "977",
	"NZ": "64", "OM": "968", "PH": "63", "PK": "92", "QA": "974", "SA": "966",
	"SG": "65", "TH": "66", "TR": "90", "US": "1", "VN": "84", "ZA": "27",
}

DEFAULT_DIAL_CODE = "92"

# National significant number lengths that are plausible for a WhatsApp line.
# Deliberately generous: the point is to catch typos, not to police numbering
# plans, and a wrongly rejected number takes the shop's contact link offline.
MIN_DIGITS = 8
MAX_DIGITS = 15


class InvalidPhoneNumber(ValueError):
	"""Raised when a number cannot be turned into a usable wa.me link."""


def normalise_whatsapp(value: str | None, dial_code: str = DEFAULT_DIAL_CODE) -> str:
	"""Public entry point used by the settings API."""
	return normalise(value, dial_code)


def normalise(value: str | None, dial_code: str = DEFAULT_DIAL_CODE) -> str:
	"""Return ``value`` as bare international digits, or ``""`` when empty.

	Accepts the forms a shopkeeper is likely to type — ``03033322111``,
	``+92 303 3322111``, ``0092-303-3322111`` — and returns ``923033322111``.
	A leading national trunk zero is dropped once the calling code is applied,
	because ``920303…`` is not a valid wa.me target.

	Raises :class:`InvalidPhoneNumber` when the result could not open a chat, so
	the caller can refuse the save rather than store a broken link.
	"""
	text = (value or "").strip()
	if not text:
		return ""

	digits = re.sub(r"\D", "", text)
	if not digits:
		# Punctuation only, e.g. "---": nothing usable, but not an error either.
		return ""

	# International access prefix ("0092…") becomes the bare calling code.
	if digits.startswith("00"):
		digits = digits[2:]

	# Decide whether the calling code is already present, then handle each form
	# once. The order matters: "923106488879" already carries "92", so it must
	# be recognised as international and left alone. Only a number that does NOT
	# start with the calling code is national, and a national number is the one
	# that carries a trunk zero ("0303…") to be dropped.
	if digits.startswith(dial_code):
		# Already international. Some write the national part with its trunk
		# zero ("+92 0303…"), which is not a valid wa.me target, so drop it.
		national = digits[len(dial_code):]
		digits = dial_code + national.lstrip("0")
	elif digits.startswith("0"):
		# National: strip the trunk zero, then add the calling code.
		digits = dial_code + digits.lstrip("0")
	else:
		# No trunk zero and no calling code: a bare national number.
		digits = dial_code + digits

	if not (MIN_DIGITS <= len(digits) <= MAX_DIGITS):
		raise InvalidPhoneNumber(
			f"{text!r} is not a usable number: it normalises to {len(digits)} digits "
			f"(a WhatsApp number needs {MIN_DIGITS}-{MAX_DIGITS}), starting {digits[:4]}…"
		)
	return digits


def catalog_url(digits: str) -> str:
	"""The catalogue deep link: ``https://wa.me/c/<number>``.

	This is the link that gives customers a shopping cart. A plain
	``https://wa.me/<number>`` opens the chat and offers no catalogue, because —
	per Meta's own documentation — Cloud API product messages do not show a cart
	icon; only the native catalogue does. So the CTA must target the catalogue.
	"""
	return f"https://wa.me/c/{digits}" if digits else ""


def chat_url(digits: str, greeting: str = "") -> str:
	"""Plain chat link, used as a fallback when the catalogue link cannot form."""
	if not digits:
		return ""
	from urllib.parse import quote

	text = quote(greeting, safe="")
	return f"https://wa.me/{digits}" + (f"?text={text}" if greeting else "")
