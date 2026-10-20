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
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

# The dot theme's palette. The ink and the accent are the storefront's own,
# so a card looks like it came from the same place as the page it links to.
INK = (11, 11, 12)
ACCENT = (229, 50, 45)
PAPER = (244, 244, 245)

FONT_DIR = Path(__file__).parent / "public" / "fonts"

# Canvas per channel. Instagram's feed takes 4:5; TikTok is 9:16.
#
# "cards" says how many a product gets on that channel. Instagram gets one
# - the product, its name and its price - because the description goes in
# the caption of the post, where there is room to write it and where it can
# be changed without redrawing anything. TikTok gets one per photograph,
# each carrying the name, the description and the price, because TikTok is
# watched with the sound off and the caption running along the bottom, so
# the words have to be on the card itself.
CHANNELS = {
	"instagram": {"label": "Instagram", "size": (1080, 1350), "cards": "front"},
	"tiktok": {"label": "TikTok", "size": (1080, 1920), "cards": "all"},
}

# Padding from the card edge to the content.
MARGIN = 64


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
	#
	# It is drawn small and stretched back up. A blur of a hundred and
	# seventy pixels over a whole card is the single most expensive thing
	# in the drawing, and at that softness the difference between blurring
	# it here and blurring it a twelfth of the size is invisible.
	small = (max(1, width // 12), max(1, height // 12))
	bloom = canvas.resize(small, Image.BOX)
	ImageDraw.Draw(bloom).ellipse(
		(int(small[0] * 0.18), int(small[1] * 0.52), int(small[0] * 1.05), int(small[1] * 1.22)),
		fill=rgb,
	)
	bloom = bloom.filter(ImageFilter.GaussianBlur(radius=max(1, width * 0.16 / 12)))
	bloom = bloom.resize((width, height), Image.BICUBIC)
	return Image.blend(canvas, bloom, 0.12)


_backgrounds: dict = {}


def background_for(tint: tuple[int, int, int], size: tuple[int, int]) -> Image.Image:
	"""The card's ground, built once and copied for each card.

	Every card of a set - the front one and all the photographs after it -
	sits on the same ground at the same size, so it is drawn once and copied
	rather than drawn ten times over.
	"""
	key = (tint, size)
	if key not in _backgrounds:
		if len(_backgrounds) > 6:
			_backgrounds.clear()
		_backgrounds[key] = background(tint, size).convert("RGBA")
	return _backgrounds[key].copy()


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


def background_colour(image: Image.Image) -> tuple[int, int, int]:
	"""The colour of the ground the product is standing on.

	Taken from the edges of the frame, which in a product shot is the sweep
	the product was photographed against.
	"""
	rgb = image.convert("RGB")
	pixels = rgb.load()
	width, height = rgb.size
	samples: list[tuple[int, int, int]] = []
	for x in range(0, width, max(1, width // 24)):
		samples.append(pixels[x, 0])
		samples.append(pixels[x, height - 1])
	for y in range(0, height, max(1, height // 24)):
		samples.append(pixels[0, y])
		samples.append(pixels[width - 1, y])
	if not samples:
		return (255, 255, 255)
	samples.sort()
	return samples[len(samples) // 2]


def product_box(image: Image.Image) -> tuple | None:
	"""Where the product is in the photograph, or None.

	The ground is read off the edges of the frame and everything that is
	not ground is the product. A shot with a busy ground gives no clean
	answer and returns None, and the photograph is then used whole - a crop
	that cut a shoe in half would be worse than a small one.
	"""
	rgb = image.convert("RGB")
	ground = background_colour(rgb)
	difference = ImageChops.difference(rgb, Image.new("RGB", rgb.size, ground))
	mask = difference.convert("L").point(lambda value: 255 if value > 40 else 0)
	box = mask.getbbox()
	if not box:
		return None

	x0, y0, x1, y1 = box
	frame = rgb.width * rgb.height
	area = (x1 - x0) * (y1 - y0)
	if area > frame * 0.88:
		# The product already fills the frame; there is nothing to gain.
		return None
	if area < frame * 0.02:
		# Too little to be a product - a speck of dust, a logo in a corner.
		return None
	return box


def crop_to_product(image: Image.Image, box=None) -> Image.Image:
	"""The photograph, cropped in on the product.

	Used for the colour the card's ground is taken from, and for nothing
	else: the picture that goes on the card is trimmed to a shape that
	holds the product rather than to the product's own bounds.
	"""
	rgb = image.convert("RGB")
	if box is None:
		box = product_box(rgb)
	if not box:
		return rgb
	x0, y0, x1, y1 = box
	# A little air around the product, so the crop does not look like it
	# cut the edges off.
	pad = int(max(x1 - x0, y1 - y0) * 0.07)
	x0 = max(0, x0 - pad)
	y0 = max(0, y0 - pad)
	x1 = min(rgb.width, x1 + pad)
	y1 = min(rgb.height, y1 + pad)
	return rgb.crop((x0, y0, x1, y1))


def prepare_photo(photo: Image.Image | None, max_width: int, max_height: int):
	"""The photograph, whole, as large as the space allows.

	Not cropped. A photograph is shown as it was taken - the whole of it,
	scaled to fit the space it is given - so nothing of the product and
	none of the scene around it is ever lost. Every trim that was made to
	square a picture up lost something: a shoe lost its heel, a bottle lost
	its lid, and a card that shows a different shape of picture from one
	product to the next looks like a mistake rather than a set.
	"""
	if not photo:
		return None, max_width, max(240, max_height)
	ratio = min(max_width / photo.width, max_height / photo.height)
	size = (max(1, round(photo.width * ratio)), max(1, round(photo.height * ratio)))
	return photo.convert("RGB").resize(size, Image.LANCZOS), size[0], size[1]


def paste_rounded(base: Image.Image, image: Image.Image, box, radius: int = 28, shadow: bool = True):
	"""A photograph on the card, with a soft shadow under it.

	One rectangle on the card: the photograph itself. The shadow is what
	stops it looking pasted on - without it the edge of the picture and
	the edge of the card are the same kind of edge, and the card reads
	flat.

	It is drawn only over the area the photograph covers rather than over
	the whole card. A blur that big is the most expensive step in drawing
	a card, and blurring an area four times the size of the shadow for the
	same result is the difference between a download that feels instant
	and one that does not.
	"""
	x, y, width, height = box
	if shadow:
		margin = 40
		scale = 4
		small_w = max(1, (width + margin * 2) // scale)
		small_h = max(1, (height + margin * 2) // scale)
		layer = Image.new("RGBA", (small_w, small_h), (0, 0, 0, 0))
		ImageDraw.Draw(layer).rounded_rectangle(
			(margin // scale, margin // scale, small_w - margin // scale, small_h - margin // scale),
			radius=max(1, radius // scale),
			fill=(11, 11, 12, 46),
		)
		layer = layer.filter(ImageFilter.BoxBlur(radius=7))
		layer = layer.resize((width + margin * 2, height + margin * 2), Image.BICUBIC)
		base.alpha_composite(layer, (x - margin, y + 18 - margin))

	mask = Image.new("L", (width, height), 0)
	ImageDraw.Draw(mask).rounded_rectangle((0, 0, width - 1, height - 1), radius=radius, fill=255)
	base.paste(image, (x, y), mask)


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


# The type and the spacing, per channel. TikTok's canvas is tall and its
# type is large, because it is read on a phone while the video runs.
LAYOUTS = {
	"instagram": {
		"margin": 64,
		"top": 64,
		"name": 58,
		"name_line": 72,
		"body": 34,
		"body_line": 48,
		"price": 34,
		"compare": 30,
		"gap": 22,
		"price_gap": 30,
	},
	"tiktok": {
		"margin": 72,
		"top": 128,
		"name": 88,
		"name_line": 104,
		"body": 46,
		"body_line": 64,
		"price": 72,
		"compare": 52,
		"gap": 28,
		"price_gap": 52,
	},
}


def price_row_measure(detail: dict, price_font, compare_font, max_width: int, draw):
	"""How tall the price row is, and whether it has to wrap.

	TikTok's price is large enough to be the biggest thing in the frame,
	and the row then does not fit across it. Rather than being clipped off
	the edge of the card, the saving goes on a line of its own.
	"""
	height = int(price_font.size * 1.9)
	price = detail["price"]
	compare = detail.get("compare_at")
	badge = f"SAVE {detail['discount']}%" if detail.get("discount") else ""
	pad = int(price_font.size * 0.9) * 2

	used = tracked_width(draw, price, price_font, 2.0) + pad
	rest = 0
	if compare:
		rest += text_width(draw, compare, compare_font) + 18
	if badge:
		rest += tracked_width(draw, badge, price_font, 2.0) + pad
	if rest and used + 18 + rest > max_width:
		return height + 16 + height, True
	return height, False


def price_row_draw(
	draw, x: int, y: int, detail: dict, price_font, compare_font, muted, wrapped: bool
):
	"""The price, the compare-at price and the saving."""
	height = int(price_font.size * 1.9)
	compare = detail.get("compare_at")
	badge = f"SAVE {detail['discount']}%" if detail.get("discount") else ""

	if wrapped:
		used = price_label(draw, x, y, detail["price"], price_font)
		y += height + 16
		used = 0
		if compare:
			strike(draw, (x + used, y + 14), compare, compare_font, muted, width=3)
			used += text_width(draw, compare, compare_font) + 18
		if badge:
			discount_flag(draw, x + used, y, badge, price_font)
		return

	used = price_label(draw, x, y, detail["price"], price_font) + 18
	if compare:
		strike(draw, (x + used, y + 14), compare, compare_font, muted, width=3)
		used += text_width(draw, compare, compare_font) + 18
	if badge:
		discount_flag(draw, x + used, y, badge, price_font)


def product_card(
	detail: dict, photo, box, channel: str, words: bool = True, description: bool = False
) -> Image.Image:
	"""One card: the photograph at the top, the words under it.

	``words`` draws the name and the price; ``description`` draws the
	description too, which only TikTok's cards carry - on Instagram the
	description goes in the caption of the post, where there is room to
	write it properly.

	The photograph is shown whole, as it was taken, and scaled to fit the
	room the words leave it. The room is the same on every card, so a set
	of them is a set.
	"""
	layout = LAYOUTS[channel]
	width, height = CHANNELS[channel]["size"]
	margin = layout["margin"]
	canvas = background_for(detail["tint"], (width, height))
	draw = ImageDraw.Draw(canvas)

	name_font = font("display", layout["name"], 700)
	body_font = font("display", layout["body"], 300)
	price_font = font("mono", layout["price"], 500)
	compare_font = font("mono", layout["compare"], 400)

	content_width = width - margin * 2
	name_lines = wrap(draw, detail["name"], name_font, content_width, 2)
	body_lines = (
		wrap(draw, detail["description"], body_font, content_width, 3) if description else []
	)

	# How much room the words take, so the photograph can be given what is
	# left of the frame.
	words_height = len(name_lines) * layout["name_line"]
	if body_lines:
		words_height += layout["gap"] + len(body_lines) * layout["body_line"]
	price_height, price_wrapped = (0, False)
	if words:
		price_height, price_wrapped = price_row_measure(
			detail, price_font, compare_font, content_width, draw
		)
		words_height += layout["price_gap"] + price_height

	top = layout["top"]
	room = height - top - margin - (words_height + layout["gap"] if words else 0)
	picture, picture_width, picture_height = prepare_photo(photo, content_width, room)

	picture_left = (width - picture_width) // 2
	picture_top = top if words else (height - picture_height) // 2

	if picture is not None:
		paste_rounded(
			canvas, picture, (picture_left, picture_top, picture_width, picture_height)
		)

	if not words:
		return canvas

	# The words sit under the photograph. The ink for them is read off the
	# card rather than assumed, so they read on whatever ground the
	# product's colour produced.
	y = picture_top + picture_height + layout["gap"]
	ink, quiet, faint = text_palette(canvas, (0, y, width, height))

	for line in name_lines:
		draw.text((margin, y), line, font=name_font, fill=ink)
		y += layout["name_line"]

	if body_lines:
		y += layout["gap"]
		for line in body_lines:
			draw.text((margin, y), line, font=body_font, fill=quiet)
			y += layout["body_line"]

	y += layout["price_gap"]
	price_row_draw(
		draw, margin, y, detail, price_font, compare_font, quiet, price_wrapped
	)

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


def prepare(doc) -> tuple[dict, list[tuple[Image.Image, tuple | None]]]:
	"""The product's details and its photographs, with where the product is.

	Done once for the whole set: every card of both channels shows the same
	photographs, so reading them twice is work for nothing.
	"""
	detail = product_detail(doc)
	photos: list[tuple[Image.Image, tuple | None]] = []
	for row in doc.images or []:
		loaded = load_photo(row.image)
		if loaded:
			photos.append((loaded, product_box(loaded)))
	if not photos and detail.get("photo"):
		photos.append((detail["photo"], product_box(detail["photo"])))
	if photos:
		# The ground is the colour of the product, not the colour of the
		# sweep it was photographed on.
		detail = {**detail, "tint": dominant_color(crop_to_product(photos[0][0], photos[0][1]))}
	return detail, photos


def render(doc, channel: str, prepared=None) -> list[tuple[str, Image.Image]]:
	"""The cards for one product on one channel, as (filename, image) pairs.

	Instagram gets the card that introduces the product, with its name and
	its price, and then one card per photograph. TikTok gets one card per
	photograph, each carrying the name, the description and the price, in
	a frame that is half product and half words.
	"""
	detail, photos = prepared if prepared else prepare(doc)
	label = CHANNELS[channel]["label"].lower()
	front = photos[0] if photos else (None, None)

	# Instagram's first card introduces the product and carries its name
	# and its price; the rest are the pictures alone, because the
	# description goes in the caption of the post. TikTok's cards each
	# carry the description as well, since TikTok is watched with the
	# sound off and the caption running along the bottom.
	with_description = channel == "tiktok"

	cards: list[tuple[str, Image.Image]] = []
	for index, (photo, box) in enumerate(photos):
		first = index == 0
		filename = f"{label}-front.jpg" if first else f"{label}-{index + 1:02d}.jpg"
		cards.append(
			(
				filename,
				product_card(
					detail,
					photo,
					box,
					channel,
					words=first or with_description,
					description=with_description,
				),
			)
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
	prepared = prepare(doc)
	with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
		for channel in CHANNELS:
			for filename, image in render(doc, channel, prepared):
				data = io.BytesIO()
				image.convert("RGB").save(data, "JPEG", quality=92, progressive=True)
				archive.writestr(f"social-cards/{channel}/{filename}", data.getvalue())

		readme = [
			doc.product_name or doc.name,
			"",
			"Social cards for Instagram and TikTok.",
			"",
			"instagram/  1080 x 1350, one card: the product, its name and its price.",
			"            The description goes in the caption of the post.",
			"tiktok/     1080 x 1920, one card per photograph, each half product",
			"            and half the name, the description and the price.",
			"",
		]
		if doc.slug:
			readme.append(f"Product: {SITE_BASE}/product/{doc.slug}")
			readme.append("")
		archive.writestr("social-cards/README.txt", "\n".join(readme))
	return buffer.getvalue()
