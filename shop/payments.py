"""Raast P2P QR: payload encoding, the QR image, and the checkout/confirmation context.

A customer who picks Raast pays by scanning a QR with their banking app — a
push payment straight into the store's account, for the whole order or for
the advance an Advance Payment setup asks up front, with the courier
collecting any balance on delivery. Advance Payment and Raast QR are one
option at the checkout for exactly that reason: both are the same transfer
to the same IBAN, one just names a smaller figure. Nothing comes back to us
afterwards (P2P has no callback), so the transfer is reconciled the same way
the advance-payment account already is: by amount, against the order the
customer was shown.

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
import os
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


def bank_code(value) -> str:
	"""The four-character bank identifier inside a Pakistani IBAN.

	`PK` + two check digits + the bank code + the account number, so the bank
	a payment is heading for can be printed straight off the number itself —
	which is the only place it is available once the QR has been downloaded
	and the settings page is nowhere in sight.
	"""
	iban = normalize_iban(value)
	return iban[4:8] if len(iban) >= 8 else ""


# Bank names for the identifiers Pakistani IBANs carry. The four characters in
# the number stay the authority: this table only spells out the banks a
# customer recognises, and any code it does not know is shown as its code
# rather than guessed at. Taken from the IBAN bank code list published at
# iban.pk (the State Bank's list of participating institutions).
BANK_NAMES = {
	"ABPA": "Allied Bank Limited",
	"AIIN": "Albaraka Bank (Pakistan) Limited",
	"ALFH": "Bank Alfalah Limited",
	"ASCM": "Askari Bank Limited",
	"BAHL": "Bank Al Habib Limited",
	"BKIP": "BankIslami Pakistan Limited",
	"BPUN": "The Bank of Punjab",
	"BURJ": "Burj Bank Limited",
	"CITI": "Citibank N.A., Pakistan",
	"DUIB": "Dubai Islamic Bank Pakistan Limited",
	"FAYS": "Faysal Bank Limited",
	"FWOM": "First Women Bank Limited",
	"HABB": "Habib Bank Limited",
	"IFBL": "IFIC Bank Limited",
	"JSBL": "JS Bank Limited",
	"KHYB": "The Bank of Khyber",
	"MBPL": "Samba Bank Limited",
	"MCIB": "MCB Islamic Bank",
	"MEZN": "Meezan Bank Limited",
	"MPBL": "Habib Metropolitan Bank Limited",
	"MUCB": "MCB Bank Limited",
	"NBPA": "National Bank of Pakistan",
	"NIBP": "NIB Bank Limited",
	"RUPB": "Rupali Bank Limited",
	"SBPP": "State Bank of Pakistan",
	"SCBL": "Standard Chartered Bank (Pakistan) Limited",
	"SIND": "Sindh Bank Limited",
	"SONE": "Soneri Bank Limited",
	"UNIL": "United Bank Limited",
}


def bank_name(value) -> str:
	"""The bank an IBAN belongs to in words, or '' when we cannot name it.

	Empty rather than the bare code so callers can decide whether a code is
	better than nothing — the confirmation panel wants a name (falling back
	to the code), the caption printed under the QR wants a bank to have been
	named or the word "Bank" in front of the identifier.
	"""
	return BANK_NAMES.get(bank_code(value), "")


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


# Faces for the caption printed under the QR. Noto is in this bench's font
# package; the rest are the usual names on other images. Pillow's own bundled
# face has no rupee glyph and would draw a tofu box, so _caption swaps it out.
_CARD_FONT_DIRS = (
	"/usr/share/fonts/truetype/noto",
	"/usr/share/fonts/truetype/dejavu",
	"/usr/share/fonts/truetype/liberation",
	"/usr/share/fonts/truetype/freefont",
	"/usr/share/fonts/TTF",
)
_CARD_FONT_FILES = (
	("NotoSans-Regular.ttf", "NotoSans-Bold.ttf"),
	("DejaVuSans.ttf", "DejaVuSans-Bold.ttf"),
	("LiberationSans-Regular.ttf", "LiberationSans-Bold.ttf"),
	("FreeSans.ttf", "FreeSansBold.ttf"),
)
_CARD_FONTS: dict = {}


def _card_font(size: int, bold: bool = False):
	"""A TrueType face for the caption, memoised by (size, bold)."""
	from PIL import ImageFont

	key = (size, bold)
	if key in _CARD_FONTS:
		return _CARD_FONTS[key]
	font = None
	for regular, heavy in _CARD_FONT_FILES:
		name = heavy if bold else regular
		for directory in _CARD_FONT_DIRS:
			path = os.path.join(directory, name)
			if os.path.exists(path):
				try:
					font = ImageFont.truetype(path, size)
				except OSError:
					continue
				break
		if font is not None:
			break
	if font is None:
		# Pillow >= 10.1 scales its embedded face; older builds take no size.
		try:
			font = ImageFont.load_default(size=size)
		except TypeError:  # pragma: no cover - Pillow is a Frappe dependency
			font = ImageFont.load_default()
	_CARD_FONTS[key] = font
	return font


def _has_glyph(font, char: str) -> bool:
	"""Whether the face draws `char` or only the same box it draws for a
	private-use codepoint (i.e. it has no glyph for it)."""
	from PIL import Image, ImageDraw

	def stamp(text: str) -> bytes:
		image = Image.new("L", (40, 40), 0)
		ImageDraw.Draw(image).text((3, 3), text, font=font, fill=255)
		return image.tobytes()

	glyph = stamp(char)
	return any(glyph) and glyph != stamp("\ue000") and glyph != stamp("\u0fff")


def _caption(text: str, font) -> str:
	"""Render `text` with the face we actually have rather than a tofu box."""
	if "\u20a8" in text and not _has_glyph(font, "\u20a8"):
		return text.replace("\u20a8", "Rs")
	return text


def _png_url(data: bytes) -> str:
	return "data:image/png;base64," + base64.b64encode(data).decode("ascii")


def qr_data_url(payload: str, headline: str = "", lines=()) -> str:
	"""PNG data URL for the payload, captioned with what the payment is for.

	Inline rather than an uploaded file: it costs one round trip to build, no
	extra request to serve, and it cannot be orphaned by a later media cleanup.
	High error correction so a scuffed screen or a slight crop still scans.

	The caption is the point of the download. A saved image outlives this
	page, so the amount, the account, the bank and the order it settles have
	to be readable from the picture alone — a gallery full of squares that
	all look alike is not a record anyone can reconcile later. Pillow is not
	an extra dependency here: Frappe itself ships it.
	"""
	if not payload or segno is None:
		return ""
	qr = io.BytesIO()
	segno.make(payload, error="h").save(qr, kind="png", scale=14, border=4)
	try:
		from PIL import Image, ImageDraw
	except ImportError:  # pragma: no cover - Pillow is a Frappe dependency
		return _png_url(qr.getvalue())

	code = Image.open(io.BytesIO(qr.getvalue())).convert("RGB")
	rows = []
	if headline:
		font = _card_font(42, bold=True)
		rows.append((_caption(headline, font), font))
	for line in lines:
		font = _card_font(24)
		rows.append((_caption(line, font), font))

	measure = ImageDraw.Draw(Image.new("RGB", (8, 8)))
	pad = 34
	row_gap = 7
	widths = [measure.textlength(text, font=font) for text, font in rows]
	heights = [measure.textbbox((0, 0), text, font=font, anchor="mt")[3] for text, font in rows]
	width = max(code.width + 2 * pad, int(max(widths, default=0)) + 2 * pad)
	# The code already carries its own four-module quiet zone; the rule is set
	# further out than that, and the caption further still.
	rule_y = pad + code.height + (24 if rows else 0)
	text_y = rule_y + (17 if rows else 0)
	height = text_y + sum(heights) + row_gap * max(0, len(rows) - 1) + pad

	card = Image.new("RGB", (width, height), (255, 255, 255))
	card.paste(code, ((width - code.width) // 2, pad))
	draw = ImageDraw.Draw(card)
	y = text_y
	if rows:
		draw.line([(pad, rule_y), (width - pad, rule_y)], fill=(127, 127, 127), width=1)
		for (text, font), line_height in zip(rows, heights):
			draw.text((width // 2, y), text, font=font, fill=(17, 17, 17), anchor="mt")
			y += line_height + row_gap
	# Down to one bit: the caption is the only antialiased part, and this URL
	# is inlined in the confirmation page, so every grey pixel it does not
	# need is a byte the customer downloads for nothing. The QR is already
	# pure black and white, so thresholding leaves it untouched.
	card = card.convert("L").point(lambda pixel: 255 if pixel >= 128 else 0)
	card = card.convert("1", dither=Image.Dither.NONE)
	out = io.BytesIO()
	card.save(out, format="PNG", optimize=True)
	return _png_url(out.getvalue())


def qr_plain_url(payload: str) -> str:
	"""PNG data URL of the code on its own, for the confirmation page.

	Same payload and error correction as the captioned card, without the
	caption: on screen every line the card prints is already on the panel
	in real text, so the picture would only be saying it twice — and a
	bare square in its quiet zone is exactly what a scanner wants to
	find. The caption stays on the download, which is the copy of this
	image that outlives the page.
	"""
	if not payload or segno is None:
		return ""
	qr = io.BytesIO()
	segno.make(payload, error="h").save(qr, kind="png", scale=14, border=4)
	return _png_url(qr.getvalue())


def configured(settings=None) -> bool:
	"""Whether the method may be offered at all: switched on, a QR encoder
	available, and an IBAN that actually passes the checksum."""
	settings = settings or frappe.get_cached_doc("Shop Settings")
	return bool(cint(settings.get("enable_raast_qr")) and segno is not None and is_valid_iban(settings.raast_iban))


def payment_context(order, settings=None) -> dict | None:
	"""Confirmation-page block for a Raast payment; None for other methods.

	Advance Payment and Raast QR are one option at checkout now, so this
	covers both shapes of order: the whole total, or the advance the customer
	agreed to with the balance left for the courier to collect. Degrades
	rather than fails: an IBAN cleared after the order was placed leaves the
	amount and instructions visible with no QR, so the customer is still told
	what they owe instead of finding an empty panel.
	"""
	if (order.get("custom_payment_method") or "cod") != "raast":
		return None

	settings = settings or frappe.get_cached_doc("Shop Settings")
	from shop.api.orders import payments_received

	# What this stage of the payment is worth. An advance is recorded on the
	# order at checkout whenever Advance Payment is switched on; with no
	# advance recorded the stage is the whole total. Whatever the ledger has
	# already been paid comes off it, because a QR for an amount that is
	# settled is a second payment waiting to happen.
	total = flt(order.grand_total)
	advance = flt(order.custom_advance_amount or 0)
	promised = advance if 0 < advance <= total else total
	balance = max(total - promised, 0.0)
	received = min(flt(payments_received([order.name]).get(order.name) or 0.0), promised)
	outstanding = max(promised - received, 0.0)
	# The headline is what is left to pay, or the stage's own figure once it
	# has been settled — "nothing due" is not a figure worth heading a panel
	# with, the status chip already says Paid.
	amount = outstanding or promised
	formatted_amount = _format_amount(amount)
	iban_raw = normalize_iban(settings.raast_iban)
	valid = is_valid_iban(iban_raw)
	payload = build_payload(iban_raw, outstanding) if valid else ""
	account_title = (settings.raast_account_title or "").strip()
	instructions = (settings.raast_payment_instructions or "").strip() or None
	# Whichever bank the money is heading for: Settings → Payments wins when
	# a name has been typed there, otherwise the IBAN names it itself — the
	# four characters after the PK and check digits are assigned to one bank
	# by the State Bank, so the number cannot disagree with the label. Only
	# when the code is one this table has never heard of does the identifier
	# stand in for a name, which is still true even if it is terse.
	named = (getattr(settings, "raast_bank_name", None) or "").strip() or bank_name(iban_raw)
	bank = named or bank_code(iban_raw)

	if not valid:
		# No usable account to point at (the detail rows below are hidden, and
		# a bad one must never be shown), so do not promise an account the page
		# cannot name — send the customer to us instead.
		line = _("Advance payment is unavailable right now. Please contact us to pay {0} by bank transfer.").format(
			formatted_amount
		)
	elif not outstanding:
		# Settled: naming a QR now would only be offering a second payment.
		line = (
			_("Advance received: {0} — the courier collects {1} on delivery.").format(
				_format_amount(promised), _format_amount(balance)
			)
			if balance > 0
			else _("Paid in full — there is nothing left to pay on this order.")
		)
	elif received > 0:
		# Part of the advance is in, so the code is for what is left of it.
		line = (
			_(
				"{0} of the {1} advance is still due — scan to settle it, then the courier collects {2} on delivery."
			).format(_format_amount(outstanding), _format_amount(promised), _format_amount(balance))
			if balance > 0
			else _("{0} of the {1} is still due — scan the code to settle it.").format(
				_format_amount(outstanding), _format_amount(promised)
			)
		)
	elif balance > 0:
		line = _(
			"Your order ships once this transfer lands — the courier collects {0} on delivery."
		).format(_format_amount(balance))
	else:
		# The how-to-scan instruction lives under the QR itself now, so this
		# line carries the only thing the headline amount cannot: what the
		# customer gets once the money has moved.
		line = _("Pay in full — your order ships once the transfer lands.")

	return {
		"configured": 1 if valid else 0,
		"line": line,
		"amount": amount,
		"formatted_amount": formatted_amount,
		"account_title": account_title,
		# One name wherever it appears: the panel row, the caption under the
		# QR and the copy block all read this, so a settings override cannot
		# leave the page telling the customer two different banks.
		"bank": bank,
		"iban": format_iban(iban_raw),
		"iban_raw": iban_raw,
		"payload": payload,
		"qr_data_url": qr_data_url(
			payload,
			headline=formatted_amount,
			# Printed under the code so a screenshot saved months later still
			# says whose account it is, which bank, and which order it settles.
			lines=[
				part
				for part in (
					account_title,
					named or f"{_('Bank')} {bank_code(iban_raw)}",
					format_iban(iban_raw),
					f"{_('Order')} {order.name}",
				)
				if part
			],
		),
		# The bare code for the page itself; the captioned one above is what
		# the download hands over.
		"qr_plain_url": qr_plain_url(payload),
		"order": order.name,
		# "Copy IBAN" is the raw value so a bank app's paste field accepts it
		# without stray spaces; "Copy details" is the block a person pastes
		# into a transfer note, order reference last so it stays visible.
		# Nothing is offered without a valid account to transfer to, nor once
		# the amount is settled — an order that is paid should not be handed
		# the means to pay it twice. An amount and an order number with no
		# destination would just send the customer chasing for details the
		# page could show.
		"copy_iban": iban_raw if valid and outstanding else "",
		"copy_details": (
			"\n".join(
				part
				for part in (
					account_title,
					named,
					format_iban(iban_raw),
					f"{_('Amount')}: {formatted_amount}",
					f"{_('Order')}: {order.name}",
				)
				if part
			)
			if valid and outstanding
			else ""
		),
		"download_name": f"raast-{order.name}.png",
		"instructions": instructions,
	}


def _format_amount(amount) -> str:
	from shop.storefront import pricing

	return pricing.format_amount(amount)
