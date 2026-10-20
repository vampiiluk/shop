"""Social cards for Instagram and TikTok.

A product's photographs are shot for a grid of white cards, not for a
story-shaped canvas with words on it. These cards are the version that works
on a phone: the product on a background taken from its own colour, the name,
one line of description, and the price as a label rather than a sentence.

Every product produces a set:

* a **front card** carrying the name, the description, the price label and,
  when there is one, the discount flag, and
* one **photo card** per remaining photograph, on the same background with a
  quiet caption.

One set per channel, because the two want different canvases. Instagram's
feed is 4:5 and TikTok is 9:16, and a card composed for one and letterboxed
into the other loses the composition it was built for.

The background is the product's own colour turned to its complement and
pulled almost all the way to white. A product shot against white sits on it
without a visible edge, and something saturated does not fight it.

Rendering is Pillow alone - no browser and no headless Chrome, so nothing has
to be installed on the server to make this work. The two brand fonts are the
same variable WOFF2 files the storefront serves, read straight by Pillow and
set to the weight each part of the card needs.

Two things the fonts decide for us:

* **Colours are opaque.** Pillow's ImageDraw *replaces* a pixel when it is
  given a colour with an alpha, it does not blend it - so a "half strength"
  grey punched a hole in the background instead of tinting the text. Every
  colour here is therefore already mixed, by ``blend``.
* **The currency is written out.** DM Mono has no rupee sign, and a font
  without a glyph draws a box. The currency code is used instead: it is what
  the card would say anyway, and it is in the font.
"""

import colorsys
import io
import os
import zipfile
from pathlib import Path

import frappe
from PIL import Image, ImageDraw, ImageFilter, ImageFont

# The dot theme's palette. The ink and the accent are the storefront's own,
# so a card looks like it came from the same place as the page it links to.
INK = (11, 11, 12)
ACCENT = (229, 50, 45)
PAPER = (244, 244, 245)

FONT_DIR = Path(__file__).parent / "public" / "fonts"

# Canvas per channel. Instagram's feed takes 4:5; TikTok is 9:16.
CHANNELS = {
	"instagram": {"label": "Instagram", "size": (1080, 1350)},
	"tiktok": {"label": "TikTok", "size": (1080, 1920)},
}

# Padding from the card edge to the content.
MARGIN = 84

_fonts: dict = {}


def font(family: str, size: int, weight: int = 400) -> ImageFont.FreeTypeFont:
	"""A brand font at one weight.

	Both fonts are variable, so the weight is an axis rather than a separate
	file: DM Mono runs 400-500 and Space Grotesk 300-700. Reading the WOFF2
	directly means the card is typeset in the same font as the storefront,
	from the same file, rather than a lookalike installed on the server.
	"""
	key = (family, size, weight)
	if key in _fonts:
		return _fonts[key]
	name = "space-grotesk.woff2" if family == "display" else "dm-mono.woff2"
	loaded = ImageFont.truetype(str(FONT_DIR / name), size)
	try:
		loaded.set_variation_by_axes([weight])
	except Exception:
		# A static font has no axis to set. The size still applies, so the
		# card is drawn with a weight the server happens to have.
		pass
	_fonts[key] = loaded
	return loaded


def blend(foreground, background, amount: float) -> tuple[int, int, int]:
	"""``foreground`` mixed into ``background`` by ``amount``.

	Pillow will not do this for us, because ImageDraw replaces a pixel rather
	than compositing over it. Mixing the colours up front is the only way to
	get a muted grey that is actually painted onto the card.
	"""
	return tuple(round(foreground[i] * amount + background[i] * (1 - amount)) for i in range(3))


def relative_luminance(rgb) -> float:
	"""The WCAG relative luminance of a colour."""

	def channel(value: float) -> float:
		value = value / 255
		return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4

	red, green, blue = (channel(c) for c in rgb)
	return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast(first, second) -> float:
	"""The WCAG contrast ratio between two colours, 1.0 to 21.0."""
	a = relative_luminance(first)
	b = relative_luminance(second)
	higher, lower = max(a, b), min(a, b)
	return (higher + 0.05) / (lower + 0.05)


def text_palette(canvas: Image.Image, region) -> tuple[tuple, tuple, tuple]:
	"""The ink, the quiet ink and the faint ink for this card.

	They are read off the card's own pixels rather than assumed. A product
	photographed against something dark used to give the card a dark ground
	and the muted text - the description, the shop's mark, the compare-at
	price - went with it, because the colour was mixed against a guess at
	what was behind it.

	So the ground is sampled where the text will actually sit, and the text
	colour is whichever of the two inks reads better on it. The muted tones
	are then mixed from that choice and pushed darker until they clear the
	contrast they are held to.
	"""
	crop = canvas.crop(region).convert("RGB")
	# A handful of samples is enough: the ground is a smooth wash, and
	# averaging a resized crop is both quick and fair.
	small = crop.resize((8, 8), Image.BOX)
	samples = [pixel for _, pixel in small.getcolors()]
	ground = tuple(round(sum(p[i] for p in samples) / len(samples)) for i in range(3))

	base = INK if contrast(INK, ground) >= contrast(PAPER, ground) else PAPER

	# The muted tones step up towards the full ink until they clear the
	# contrast they are held to, so a quiet label is still readable on
	# whatever ground the card ended up with.
	quiet = base
	amount = 0.62
	while amount < 1.0:
		quiet = blend(base, ground, amount)
		if contrast(quiet, ground) >= 4.5:
			break
		amount = min(1.0, amount + 0.06)

	faint = base
	amount = 0.34
	while amount < 1.0:
		faint = blend(base, ground, amount)
		if contrast(faint, ground) >= 3.0:
			break
		amount = min(1.0, amount + 0.06)

	return base, quiet, faint


# --- text helpers ---------------------------------------------------------------


def text_width(draw: ImageDraw.ImageDraw, text: str, fnt) -> float:
	return draw.textlength(text, font=fnt)


def wrap(draw, text: str, fnt, max_width: int, max_lines: int) -> list[str]:
	"""Break ``text`` into at most ``max_lines`` lines that fit ``max_width``.

	The last line is trimmed with an ellipsis when the text does not fit, so a
	long name is shortened rather than allowed to run off the card.
	"""
	text = " ".join((text or "").split())
	if not text:
		return []
	lines: list[str] = []
	current = ""
	overflowed = False
	for word in text.split(" "):
		candidate = f"{current} {word}".strip()
		if text_width(draw, candidate, fnt) <= max_width or not current:
			current = candidate
			continue
		lines.append(current)
		current = word
		if len(lines) == max_lines:
			overflowed = True
			break
	if not overflowed and current:
		lines.append(current)
	if overflowed:
		lines[-1] = _trim(draw, f"{lines[-1]} {current}…", fnt, max_width)
	return lines[:max_lines]


def _trim(draw, text: str, fnt, max_width: int) -> str:
	if text_width(draw, text, fnt) <= max_width:
		return text
	cut = text
	while cut and text_width(draw, cut + "…", fnt) > max_width:
		cut = cut[:-1]
	return cut.rstrip() + "…"


def draw_tracked(draw, xy, text: str, fnt, fill, tracking: float) -> None:
	"""Draw text with letterspacing.

	The storefront sets its labels in DM Mono at a quarter-em of tracking, and
	that is most of what makes a small label look like a label rather than a
	word. Pillow has no letterspacing, so the glyphs are placed by hand.
	"""
	x, y = xy
	for char in text:
		draw.text((x, y), char, font=fnt, fill=fill)
		x += text_width(draw, char, fnt) + tracking


def tracked_width(draw, text: str, fnt, tracking: float) -> float:
	if not text:
		return 0
	return sum(text_width(draw, char, fnt) for char in text) + tracking * (len(text) - 1)


def strike(draw, xy, text: str, fnt, fill, width: int = 2) -> None:
	"""Text with a line through it, for the compare-at price.

	The line sits above the middle of the glyphs, where a strike belongs on
	digits - through the middle it cuts the numerals in half and the price
	becomes unreadable.
	"""
	x, y = xy
	draw.text((x, y), text, font=fnt, fill=fill)
	box = draw.textbbox((x, y), text, font=fnt)
	line_y = box[1] + (box[3] - box[1]) * 0.36
	draw.line((box[0], line_y, box[2], line_y), fill=fill, width=width)


# --- colour ---------------------------------------------------------------------


def dominant_color(image: Image.Image) -> tuple[int, int, int]:
	"""The colour that best represents the product.

	Not simply the most common colour: a product shot on a tiled floor is
	mostly floor, and the floor's grey would be picked over the shoe. So a
	colour is scored by how much of the frame it fills *and* by how saturated
	it is, which lets the product's own colour beat the ground it stands on.
	"""
	small = image.convert("RGB").resize((64, 64))
	quantized = small.quantize(colors=8, method=Image.Quantize.MEDIANCUT)
	palette = quantized.getpalette() or []
	counts = sorted(quantized.getcolors() or [], reverse=True)
	if not counts:
		return (150, 150, 150)

	scored = []
	for count, index in counts:
		rgb = tuple(palette[index * 3 : index * 3 + 3])
		if len(rgb) != 3:
			continue
		hue, lightness, saturation = colorsys.rgb_to_hls(*(c / 255 for c in rgb))
		if not 0.08 < lightness < 0.93:
			# A blown-out sweep or a black ground says nothing about the
			# product; skip it if there is anything else to pick.
			continue
		scored.append((count * (0.35 + saturation), rgb))
	if not scored:
		return (150, 150, 150)
	scored.sort(key=lambda row: row[0], reverse=True)
	return scored[0][1]


def background(rgb: tuple[int, int, int], size: tuple[int, int]) -> Image.Image:
	"""A soft wash built from the complement of the product's colour.

	The complement is what "complementing" means here: the hue opposite the
	product, so a warm product sits on a cool ground and a cool one on a warm
	ground. It is then pulled almost to white and nearly drained of colour, so
	the ground stays a backdrop - it reads as deliberate without ever competing
	with the product for attention.

	Two things the ground must never be. It must not be dark, because the
	text sits on it and a dark ground swallows the muted parts of the card.
	And it must not be the product's own colour at full strength, because
	then it stops being a ground and becomes a second subject.

	So the wash is built light and stays light, and the product's colour
	arrives as a bloom over the top of it at a strength that cannot take the
	card down.
	"""
	width, height = size
	hue, _, _ = colorsys.rgb_to_hls(*(c / 255 for c in rgb))
	hue = (hue + 0.5) % 1.0
	# hls_to_rgb answers in 0..1 and an 8-bit pixel wants 0..255. The scale
	# is done here; left to the pixel, a value of 0.95 lands as 1 and the
	# whole card comes out black.
	top = tuple(round(c * 255) for c in colorsys.hls_to_rgb(hue, 0.955, 0.075))
	bottom = tuple(round(c * 255) for c in colorsys.hls_to_rgb(hue, 0.995, 0.015))

	strip = Image.new("RGB", (1, height))
	pixels = strip.load()
	for y in range(height):
		t = y / max(height - 1, 1)
		pixels[0, y] = tuple(round(top[i] * (1 - t) + bottom[i] * t) for i in range(3))
	canvas = strip.resize((width, height))

	# One large, very soft bloom of the product's own colour, low in the
	# frame. It keeps the wash from reading as a flat gradient.
	#
	# The bloom starts as a copy of the wash, not as black with a shape
	# painted on it: a black base would drag the entire card down with it,
	# which is how a dark product ended up with a black ground.
	bloom = canvas.copy()
	ImageDraw.Draw(bloom).ellipse(
		(int(width * 0.18), int(height * 0.52), int(width * 1.05), int(height * 1.22)),
		fill=rgb,
	)
	bloom = bloom.filter(ImageFilter.GaussianBlur(radius=width * 0.16))
	return Image.blend(canvas, bloom, 0.12)


# --- product photos -------------------------------------------------------------


def load_photo(url: str) -> Image.Image | None:
	"""The product's photograph, or None if the file is not there.

	An image row is only a url; the file behind it can be gone. A card without
	a photo is still worth making, so this returns None rather than raising.
	"""
	from shop.files import site_file_path

	path = site_file_path(url)
	if not path or not os.path.isfile(path):
		return None
	try:
		image = Image.open(path)
		image.load()
		return image.convert("RGB")
	except Exception:
		return None


def fit(image: Image.Image, max_width: int, max_height: int) -> tuple[Image.Image, int, int]:
	"""Scale down into a box, keeping the aspect ratio."""
	ratio = min(max_width / image.width, max_height / image.height, 1.0)
	size = (max(1, round(image.width * ratio)), max(1, round(image.height * ratio)))
	return image.resize(size, Image.LANCZOS), size[0], size[1]


def paste_rounded(base: Image.Image, image: Image.Image, box, radius: int, shadow: bool = True):
	"""Drop a photo into a rounded rectangle, with a soft shadow under it.

	The shadow is what stops the photo from looking pasted on: without it the
	edge of the picture and the edge of the card are the same kind of edge, and
	the whole card reads flat.
	"""
	x, y, width, height = box
	if shadow:
		layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
		ImageDraw.Draw(layer).rounded_rectangle(
			(x, y + 18, x + width, y + height + 18),
			radius=radius,
			fill=(11, 11, 12, 46),
		)
		layer = layer.filter(ImageFilter.GaussianBlur(radius=26))
		base.alpha_composite(layer)

	mask = Image.new("L", (width, height), 0)
	ImageDraw.Draw(mask).rounded_rectangle((0, 0, width - 1, height - 1), radius=radius, fill=255)
	base.paste(image, (x, y), mask)


# --- card parts -----------------------------------------------------------------


def price_label(draw, x: int, y: int, text: str, fnt, fill=INK, color=PAPER) -> int:
	"""The price, as a label rather than a number in a sentence.

	Returns the width it took, so the caller can lay the row out around it.
	"""
	tracking = 2.0
	width = tracked_width(draw, text, fnt, tracking)
	height = int(fnt.size * 1.9)
	pad_x = int(fnt.size * 0.9)
	box_width = round(width + pad_x * 2)
	draw.rounded_rectangle((x, y, x + box_width, y + height), radius=height // 2, fill=fill)
	draw_tracked(draw, (x + pad_x, y + (height - fnt.size) / 2 - 2), text, fnt, color, tracking)
	return box_width


def discount_flag(draw, x: int, y: int, text: str, fnt) -> int:
	"""The saving, in the storefront's accent.

	Accent with an ink label, the same pairing the red buttons use, which is
	legible on both the light and the dark palette.
	"""
	tracking = 2.0
	width = tracked_width(draw, text, fnt, tracking)
	height = int(fnt.size * 1.9)
	pad_x = int(fnt.size * 0.9)
	box_width = round(width + pad_x * 2)
	draw.rounded_rectangle((x, y, x + box_width, y + height), radius=height // 2, fill=ACCENT)
	draw_tracked(draw, (x + pad_x, y + (height - fnt.size) / 2 - 2), text, fnt, INK, tracking)
	return box_width


# --- cards ----------------------------------------------------------------------


def front_card(detail: dict, channel: str) -> Image.Image:
	"""The card that carries the product's name, description and price."""
	width, height = CHANNELS[channel]["size"]
	canvas = background(detail["tint"], (width, height)).convert("RGBA")
	draw = ImageDraw.Draw(canvas)

	# The card's own ground, sampled where nothing is drawn on it, so the
	# muted text can be mixed against the colour actually behind it.
	eyebrow_font = font("mono", 26, 500)

	name_font = font("display", 62, 700)
	body_font = font("display", 32, 300)
	price_font = font("mono", 30, 500)
	compare_font = font("mono", 28, 400)

	content_width = width - MARGIN * 2
	name_lines = wrap(draw, detail["name"], name_font, content_width, 2)
	body_lines = wrap(draw, detail["description"], body_font, content_width, 2)

	name_height = len(name_lines) * 76
	body_height = len(body_lines) * 46
	text_height = name_height + (18 if body_lines else 0) + body_height + 44 + 62

	# The photo and the words are one group, and the group is placed in the
	# frame rather than hung from the top of it, so a tall canvas does not
	# leave the card with a hole in the middle. A little above centre: the
	# bottom of a phone screen is where the caption of a post lives.
	eyebrow_bottom = MARGIN + 56
	bottom = height - MARGIN
	room = bottom - eyebrow_bottom - text_height - 56
	photo_height = max(240, min(room, int(height * 0.62)))

	photo = detail.get("photo")
	if photo:
		photo, photo_w, photo_h = fit(photo, content_width, photo_height)
	else:
		photo_w, photo_h = content_width, photo_height

	group_height = photo_h + 56 + text_height
	group_top = eyebrow_bottom + round((bottom - eyebrow_bottom - group_height) * 0.32)
	photo_top = group_top

	# The ink is read off the card, in the band the words will occupy,
	# before anything is painted on it. The text then goes down in whichever
	# ink reads on that ground, rather than in an ink that was assumed - a
	# dark product used to get a dark ground and the muted parts of the
	# card went with it.
	text_top = photo_top + photo_h + 56
	ink, quiet, faint = text_palette(canvas, (0, text_top, width, height))
	# The eyebrow sits at the top of the card, where the wash is a shade
	# different from the band the words are in, so it is read on its own.
	_, eyebrow_ink, _ = text_palette(canvas, (0, 0, width, eyebrow_bottom))

	draw_tracked(
		draw, (MARGIN, MARGIN - 6), detail["store_name"].upper(), eyebrow_font, eyebrow_ink, 5.0
	)

	if photo:
		paste_rounded(canvas, photo, ((width - photo_w) // 2, photo_top, photo_w, photo_h), radius=28)
	else:
		placeholder = Image.new("RGBA", (photo_w, photo_h), (255, 255, 255, 0))
		ImageDraw.Draw(placeholder).rounded_rectangle(
			(0, 0, placeholder.width - 1, placeholder.height - 1),
			radius=28,
			fill=(255, 255, 255, 150),
		)
		canvas.alpha_composite(placeholder, ((width - photo_w) // 2, photo_top))

	y = text_top

	for line in name_lines:
		draw.text((MARGIN, y), line, font=name_font, fill=ink)
		y += 76

	if body_lines:
		y += 18
		for line in body_lines:
			draw.text((MARGIN, y), line, font=body_font, fill=quiet)
			y += 46

	y += 44
	x = MARGIN
	x += price_label(draw, x, y, detail["price"], price_font) + 18
	if detail.get("compare_at"):
		compare = detail["compare_at"]
		strike(draw, (x, y + 14), compare, compare_font, quiet)
		x += text_width(draw, compare, compare_font) + 18
	if detail.get("discount"):
		discount_flag(draw, x, y, f"SAVE {detail['discount']}%", price_font)

	# The shop's name, bottom right, small enough to be a mark rather than
	# a claim.
	mark_font = font("mono", 24, 500)
	mark = detail["store_name"].upper()
	mark_width = tracked_width(draw, mark, mark_font, 5.0)
	draw_tracked(draw, (width - MARGIN - mark_width, bottom + 10), mark, mark_font, faint, 5.0)

	return canvas


def photo_card(detail: dict, channel: str, index: int) -> Image.Image:
	"""One of the remaining photographs, on the same ground, quietly captioned."""
	width, height = CHANNELS[channel]["size"]
	canvas = background(detail["tint"], (width, height)).convert("RGBA")
	draw = ImageDraw.Draw(canvas)

	name_font = font("display", 44, 500)
	price_font = font("mono", 28, 500)
	index_font = font("mono", 24, 400)

	content_width = width - MARGIN * 2
	name_lines = wrap(draw, detail["name"], name_font, content_width, 1)
	text_height = len(name_lines) * 56 + 30 + 56

	photo = detail.get("photo")
	if photo:
		photo, photo_w, photo_h = fit(photo, content_width, max(240, height - MARGIN * 2 - text_height - 52))
	else:
		photo_w, photo_h = content_width, max(240, height - MARGIN * 2 - text_height - 52)

	# The photo and its caption are one group, and the group sits in the
	# frame rather than hanging from the top of it. A little above centre,
	# because the bottom of a phone screen is where the caption of a post
	# lives.
	group_height = photo_h + 52 + text_height
	group_top = round((height - group_height) * 0.4)

	photo_top = group_top

	# As on the front card, the ink is read off the card rather than
	# assumed, so the caption reads on whatever ground the product's colour
	# produced.
	text_top = photo_top + photo_h + 52
	ink, quiet, faint = text_palette(canvas, (0, text_top, width, height))

	if photo:
		paste_rounded(canvas, photo, ((width - photo_w) // 2, photo_top, photo_w, photo_h), radius=28)
	else:
		placeholder = Image.new("RGBA", (photo_w, photo_h), (255, 255, 255, 0))
		ImageDraw.Draw(placeholder).rounded_rectangle(
			(0, 0, placeholder.width - 1, placeholder.height - 1),
			radius=28,
			fill=(255, 255, 255, 150),
		)
		canvas.alpha_composite(placeholder, ((width - photo_w) // 2, photo_top))

	y = text_top
	for line in name_lines:
		draw.text((MARGIN, y), line, font=name_font, fill=ink)
		y += 56

	price_label(draw, MARGIN, y + 30, detail["price"], price_font)

	# A quiet index, so a set of photo cards reads as a sequence.
	mark = f"{index:02d}"
	mark_width = tracked_width(draw, mark, index_font, 4.0)
	draw_tracked(draw, (width - MARGIN - mark_width, y + 38), mark, index_font, faint, 4.0)

	return canvas


# --- the set ---------------------------------------------------------------------


def money(amount: float, currency: str) -> str:
	"""A price written the way the card can render it.

	The currency code, not the symbol: DM Mono has no rupee sign and draws a
	box for one. Decimals are dropped on a whole amount, which is how a price
	on a poster is written anyway.
	"""
	if not amount:
		return ""
	if round(amount, 2) == int(amount):
		return f"{currency} {int(amount):,}"
	return f"{currency} {amount:,.2f}"


def product_detail(doc) -> dict:
	"""Everything a card needs about a product, in one place."""
	from shop.api.products import sellable_codes
	from shop.storefront import pricing

	settings = frappe.get_cached_doc("Shop Settings")
	store_name = (settings.store_name or "ReeLoop").strip() or "ReeLoop"
	currency = (settings.currency or "PKR").strip() or "PKR"

	price = 0.0
	if doc.has_variants:
		codes = sellable_codes(doc.item, doc.has_variants)
		rates = [r["rate"] for r in pricing.get_prices(codes).values() if r.get("rate")]
		if rates:
			price = min(rates)
	else:
		price = (pricing.get_price(doc.item) or {}).get("rate") or 0.0

	compare_at = 0.0
	compare_price = float(doc.compare_at_price or 0)
	if price and compare_price > price:
		compare_at = compare_price

	discount = 0
	if compare_at and price:
		discount = round((compare_at - price) * 100 / compare_at)

	name = (doc.product_name or doc.name).strip()
	description = (doc.short_description or "").strip()
	# A description that only repeats the name is noise on a card that
	# already carries the name.
	if description.lower() == name.lower():
		description = ""

	photo = None
	tint = (198, 198, 200)
	for row in doc.images or []:
		loaded = load_photo(row.image)
		if loaded:
			photo = loaded
			tint = dominant_color(loaded)
			break

	return {
		"name": name,
		"description": description,
		"store_name": store_name,
		"price": money(price, currency),
		"compare_at": money(compare_at, currency) if compare_at else "",
		"discount": discount,
		"photo": photo,
		"tint": tint,
	}


def render(doc, channel: str) -> list[tuple[str, Image.Image]]:
	"""The cards for one product on one channel, as (filename, image) pairs.

	The first photograph becomes the front card, which carries the name, the
	description and the price. The rest become photo cards on the same
	background.
	"""
	detail = product_detail(doc)
	photos = []
	for row in doc.images or []:
		loaded = load_photo(row.image)
		if loaded:
			photos.append(loaded)
	if not photos and detail.get("photo"):
		photos.append(detail["photo"])

	label = CHANNELS[channel]["label"].lower()
	cards: list[tuple[str, Image.Image]] = []
	front_photo = photos[0] if photos else None
	cards.append((f"{label}-front.jpg", front_card({**detail, "photo": front_photo}, channel)))

	for index, photo in enumerate(photos[1:], start=2):
		cards.append(
			(f"{label}-{index:02d}.jpg", photo_card({**detail, "photo": photo}, channel, index))
		)
	return cards


def safe_filename(name: str) -> str:
	"""A name that is safe to write on a filesystem and to read in a list.

	The product's own name is what the archive is called, so it has to
	survive the trip through a Content-Disposition header: no path
	separators, no control characters, no leading dots, and a length that a
	download manager will not truncate in the middle.
	"""
	cleaned = "".join(
		character
		for character in (name or "").strip()
		if character.isprintable() and character not in '\\/:*?"<>|'
	)
	cleaned = " ".join(cleaned.split()).strip(". ")
	return cleaned[:120] or "product"


def build_zip(doc) -> bytes:
	"""Every card for a product, both channels, as one zip."""
	from shop.storefront.urls import SITE_BASE

	buffer = io.BytesIO()
	with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
		for channel in CHANNELS:
			for filename, image in render(doc, channel):
				data = io.BytesIO()
				image.convert("RGB").save(data, "JPEG", quality=92, optimize=True, progressive=True)
				archive.writestr(f"social-cards/{channel}/{filename}", data.getvalue())

		readme = [
			doc.product_name or doc.name,
			"",
			"Social cards for Instagram and TikTok.",
			"",
			"instagram/  1080 x 1350, the front card first, then one card per photo.",
			"tiktok/     1080 x 1920, the same set in a vertical frame.",
			"",
		]
		if doc.slug:
			readme.append(f"Product: {SITE_BASE}/product/{doc.slug}")
			readme.append("")
		archive.writestr("social-cards/README.txt", "\n".join(readme))
	return buffer.getvalue()
