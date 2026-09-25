"""Raast P2P QR: payload encoding, the QR image, and the checkout/confirmation context.

A customer who picks Raast pays the whole order by scanning a QR with their
banking app — a push payment straight into the store's account. Nothing comes
back to us afterwards (P2P has no callback), so the transfer is reconciled the
same way the advance-payment account already is: by amount, against the order
the customer was shown.

The payload is the SBP P2P template from "Standard for Interoperable QR Code"
(DI&SD Circular Letter No. 01 of 2022, section 3.1)::

    00 02 "02"          payload format indicator — 02 is assigned to P2P
    01 02 "11"|"12"     point of initiation — static when no amount is encoded
    02 02 "30"          scheme identifier — 30 Raast P2P, 31 1-Link (mandatory)
    04 24 <IBAN>        beneficiary IBAN (mandatory)
    05 nn <amount>      amount — conditional, present because ours is fixed
    10 04 <CRC16>       EMVCo QRCPS checksum over everything above plus "1004"

Tag 03 (FI name) and tag 06 (particulars) are optional and left out so the
payload stays minimal; tag 07 is reserved for future use by SBP, which is why
there is no expiry — a checkout QR should stay valid until the order is paid
rather than quietly going stale. The QR itself is rendered as a PNG data URL so
the confirmation page needs no extra request for it.
"""

import base64
import io
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import frappe
from frappe import _
from frappe.utils import cint, flt

try:
	import segno
except ImportError:  # pragma: no cover - declared in requirements.txt
	segno = None

# SBP P2P template constants (see the module docstring).
P2P_FORMAT = "02"
POI_STATIC = "11"
POI_DYNAMIC = "12"
SCHEME_RAAST = "30"
CRC_TAG = "1004"

# IBANs are 30 chars max per ISO 13616, but tag 04 in the SBP template is
# fixed at 24 — Pakistan's own length.
IBAN_LENGTH = 24
# Digits plus the single decimal point, no longer than the template allows.
AMOUNT_MAX_LEN = 10


def normalize_iban(value) -> str:
	"""Strip the spacing people paste and upper-case it."""
	if not value:
		return ""
	return "".join(str(value).split()).upper()


def is_valid_iban(value) -> bool:
	"""Shape check for a Pakistani IBAN plus the ISO 13616 mod-97 checksum.

	The checksum is what makes a typo in Settings obvious: a wrong digit
	silently sends money to an account that does not exist, and nothing here
	would ever notice.
	"""
	iban = normalize_iban(value)
	if len(iban) != IBAN_LENGTH or not iban.startswith("PK") or not iban.isalnum():
		return False
	return _mod97(iban) == 1


def _mod97(iban: str) -> int:
	"""ISO 13616 check: move the country + check digits to the end, map letters
	to numbers, take the remainder. The value must be 1 for a valid IBAN."""
	rearranged = iban[4:] + iban[:4]
	digits = "".join(str(ord(char) - 55) if char.isalpha() else char for char in rearranged)
	# Chunked so the divisor never needs big-integer arithmetic.
	remainder = 0
	for char in digits:
		remainder = (remainder * 10 + int(char)) % 97
	return remainder


def format_iban(value) -> str:
	"""Group the IBAN in fours for display: PK33 ABCD 0000 ..."""
	iban = normalize_iban(value)
	return " ".join(iban[index : index + 4] for index in range(0, len(iban), 4))


def normalize_amount(value) -> str:
	"""Amount for tag 05: whole or two-decimal digits, never zero or longer
	than the template's ten characters."""
	try:
		amount = Decimal(str(flt(value))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
	except (InvalidOperation, ValueError, TypeError):
		return ""
	if not amount.is_finite() or amount <= 0:
		return ""
	text = format(amount, "f")
	if "." in text:
		text = text.rstrip("0").rstrip(".")
	return text if 0 < len(text) <= AMOUNT_MAX_LEN else ""


def crc16_ccitt_false(data: str) -> str:
	"""CRC-16/CCITT-FALSE — poly 0x1021, init 0xFFFF, no reflection, no xorout.

	This is the checksum EMVCo QRCPS specifies for QR payment payloads, and
	what the SBP template's tag 10 asks for. The checksum covers the literal
	"1004" (tag 10 with length 04) as part of the data, the same way every
	other implementation of the standard does it.
	"""
	crc = 0xFFFF
	for byte in data.encode("utf-8"):
		crc ^= byte << 8
		for _ in range(8):
			crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
	return f"{crc:04X}"


def tlv(tag: str, value: str) -> str:
	"""One tag-length-value record: the tag, its length in two digits, then the
	value itself."""
	return f"{tag}{len(value):02d}{value}"


def build_payload(iban: str, amount) -> str:
	"""Encode the Raast P2P payload; empty when the IBAN or amount is unusable."""
	iban = normalize_iban(iban)
	if not is_valid_iban(iban):
		return ""
	value = normalize_amount(amount)
	if not value:
		return ""
	# The amount is fixed by this code, so the point of initiation is dynamic.
	body = (
		tlv("00", P2P_FORMAT)
		+ tlv("01", POI_DYNAMIC)
		+ tlv("02", SCHEME_RAAST)
		+ tlv("04", iban)
		+ tlv("05", value)
		+ CRC_TAG
	)
	return body + crc16_ccitt_false(body)


def qr_data_url(payload: str) -> str:
	"""PNG data URL for the payload.

	Inline rather than an uploaded file: it costs one round trip to build, no
	extra request to serve, and it cannot be orphaned by a later media cleanup.
	High error correction so a scuffed screen or a slight crop still scans.
	"""
	if not payload or segno is None:
		return ""
	buffer = io.BytesIO()
	segno.make(payload, error="h").save(buffer, kind="png", scale=14, border=4)
	return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def configured(settings=None) -> bool:
	"""Whether the method may be offered at all: switched on, a QR encoder
	available, and an IBAN that actually passes the checksum."""
	settings = settings or frappe.get_cached_doc("Shop Settings")
	return bool(cint(settings.get("enable_raast_qr")) and segno is not None and is_valid_iban(settings.raast_iban))


def payment_context(order, settings=None) -> dict | None:
	"""Confirmation-page block for a Raast payment; None for other methods.

	Degrades rather than fails: an IBAN cleared after the order was placed
	leaves the amount and instructions visible with no QR, so the customer is
	still told what they owe instead of finding an empty tile.
	"""
	if (order.get("custom_payment_method") or "cod") != "raast":
		return None

	settings = settings or frappe.get_cached_doc("Shop Settings")
	amount = flt(order.grand_total)
	formatted_amount = _format_amount(amount)
	iban_raw = normalize_iban(settings.raast_iban)
	valid = is_valid_iban(iban_raw)
	payload = build_payload(iban_raw, amount) if valid else ""
	account_title = (settings.raast_account_title or "").strip()
	instructions = (settings.raast_payment_instructions or "").strip() or None

	if valid:
		line = _("Scan the code with your banking app to pay {0} in full. Your order ships once the transfer lands.").format(
			formatted_amount
		)
	else:
		# No usable account to point at (the IBAN row is hidden below, and a
		# bad one must never be shown), so do not promise an account the page
		# cannot name — send the customer to us instead.
		line = _("Raast payment is unavailable right now. Please contact us to pay {0} by bank transfer.").format(
			formatted_amount
		)

	return {
		"configured": 1 if valid else 0,
		"line": line,
		"amount": amount,
		"formatted_amount": formatted_amount,
		"account_title": account_title,
		"iban": format_iban(iban_raw),
		"iban_raw": iban_raw,
		"payload": payload,
		"qr_data_url": qr_data_url(payload),
		"order": order.name,
		# "Copy IBAN" is the raw value so a bank app's paste field accepts it
		# without stray spaces; "Copy details" is the block a person pastes
		# into a transfer note, order reference last so it stays visible.
		# Without a valid account there is nothing to transfer to, so neither
		# is offered: an amount and an order number with no destination would
		# just send the customer chasing for details the page could show.
		"copy_iban": iban_raw if valid else "",
		"copy_details": (
			"\n".join(
				part
				for part in (
					account_title,
					format_iban(iban_raw),
					f"{_('Amount')}: {formatted_amount}",
					f"{_('Order')}: {order.name}",
				)
				if part
			)
			if valid
			else ""
		),
		"download_name": f"raast-{order.name}.png",
		"instructions": instructions,
	}


def _format_amount(amount) -> str:
	from shop.storefront import pricing

	return pricing.format_amount(amount)
