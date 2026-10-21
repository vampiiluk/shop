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


def wrap_all(draw, text: str, fnt, max_width: int) -> list[str]:
	"""Every line the text needs, none of them trimmed."""
	text = " ".join((text or "").split())
	if not text:
		return []
	lines: list[str] = []
	current = ""
	for word in text.split(" "):
		candidate = f"{current} {word}".strip()
		if text_width(draw, candidate, fnt) <= max_width or not current:
			current = candidate
		else:
			lines.append(current)
			current = word
	if current:
		lines.append(current)
	return lines


def fit_name(draw, text: str, size: int, min_size: int, max_width: int, max_lines: int):
	"""The product's name, whole, at the largest size that fits.

	A product's name is the name, not a summary of it, so it is never cut
	off with an ellipsis: the type gets smaller instead. Only if even the
	smallest size will not fit does the name get the lines it needs.
	"""
	while size > min_size:
		fnt = font("display", size, 700)
		lines = wrap_all(draw, text, fnt, max_width)
		if len(lines) <= max_lines:
			return lines, fnt, size
		size -= 2
	fnt = font("display", min_size, 700)
	return wrap_all(draw, text, fnt, max_width), fnt, min_size


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


_logos: dict = {}


def store_logo(size: int) -> Image.Image | None:
	"""The shop's logo, as ink on nothing.

	The logo is a black mark on a white square, so the white is taken out
	of it before it goes on a card - a white block sitting on a cream
	ground reads as a mistake rather than as a logo. The mark is redrawn in
	the card's ink so it belongs to the same set of type as the words.
	"""
	if size in _logos:
		return _logos[size]
	_logos[size] = None

	settings = frappe.get_cached_doc("Shop Settings")
	if not settings.store_logo:
		return None
	from shop.files import site_file_path

	path = site_file_path(settings.store_logo)
	if not path or not os.path.isfile(path):
		return None
	try:
		grey = Image.open(path)
		grey.load()
		grey = grey.convert("L")
		# Everything that is not the mark is the background it was saved on.
		mask = grey.point(lambda value: 0 if value > 235 else 255)
		bounds = mask.getbbox()
		if not bounds:
			return None
		mask = mask.crop(bounds)
		scale = size / mask.height
		mask = mask.resize((max(1, round(mask.width * scale)), size), Image.LANCZOS)
		mark = Image.new("RGBA", mask.size, INK + (0,))
		mark.putalpha(mask)
	except Exception:
		return None
	_logos[size] = mark
	return mark


# --- cards ----------------------------------------------------------------------


# The type and the spacing, per channel. TikTok's canvas is tall and its
# type is large, because it is read on a phone while the video runs.
LAYOUTS = {
	"instagram": {
		"margin": 36,
		"pad": 30,
		"logo": 46,
		"title": 46,
		"title_line": 54,
		"body": 29,
		"body_line": 40,
		"price": 76,
		"compare": 38,
		"label": 18,
		"option": 27,
		"swatch": 34,
		"gap": 22,
	},
	"tiktok": {
		"margin": 40,
		"pad": 36,
		"logo": 58,
		"title": 62,
		"title_line": 72,
		"body": 38,
		"body_line": 52,
		"price": 80,
		"compare": 40,
		"label": 22,
		"option": 36,
		"swatch": 46,
		"gap": 28,
	},
}

# The grey the small print is in, and the line around a colour swatch.
MUTED = (107, 114, 128)
HAIRLINE = (229, 231, 235)

# The colours a swatch can be, by name. A colour the shop has no name for
# gets a neutral grey, which is honest: better a grey swatch than a wrong
# one.
SWATCH_COLOURS = {
	"black": (26, 26, 26),
	"white": (255, 255, 255),
	"grey": (132, 134, 138),
	"gray": (132, 134, 138),
	"charcoal": (54, 57, 62),
	"silver": (192, 193, 196),
	"red": (206, 32, 39),
	"maroon": (112, 22, 34),
	"burgundy": (120, 20, 42),
	"wine": (110, 26, 46),
	"pink": (232, 96, 156),
	"rose": (226, 130, 152),
	"blush": (238, 190, 196),
	"magenta": (200, 26, 108),
	"blue": (34, 74, 186),
	"navy": (26, 40, 66),
	"sky": (128, 186, 226),
	"teal": (22, 122, 116),
	"green": (36, 132, 74),
	"olive": (104, 124, 48),
	"lime": (150, 186, 62),
	"mint": (158, 214, 190),
	"yellow": (240, 196, 44),
	"gold": (198, 160, 58),
	"mustard": (198, 150, 40),
	"orange": (232, 108, 36),
	"rust": (176, 82, 40),
	"brown": (112, 72, 44),
	"tan": (206, 178, 136),
	"beige": (222, 206, 176),
	"cream": (244, 234, 208),
	"khaki": (154, 146, 92),
	"purple": (112, 58, 178),
	"violet": (132, 96, 200),
	"coral": (238, 130, 104),
	"peach": (240, 196, 168),
	"sand": (206, 182, 142),
	"wine red": (110, 26, 46),
}


def swatch_colour(name: str) -> tuple[int, int, int]:
	"""The colour a swatch for this name is drawn in."""
	key = " ".join((name or "").strip().lower().split())
	if key in SWATCH_COLOURS:
		return SWATCH_COLOURS[key]
	for word, colour in SWATCH_COLOURS.items():
		if word in key:
			return colour
	return (150, 152, 156)


def header_colour(tint: tuple[int, int, int]) -> tuple[int, int, int]:
	"""The colour of the bar at the head of the card.

	Taken from the product's own colour and made strong enough to carry
	white text: the colour in the photograph is often a washed-out grey
	from a studio sweep, and a grey bar with white on it does not read.
	"""
	hue, lightness, saturation = colorsys.rgb_to_hls(*(c / 255 for c in tint))
	saturation = max(saturation, 0.55)
	lightness = min(max(lightness, 0.30), 0.46)
	colour = INK
	while lightness > 0.16:
		red, green, blue = colorsys.hls_to_rgb(hue, lightness, saturation)
		colour = (round(red * 255), round(green * 255), round(blue * 255))
		if contrast(PAPER, colour) >= 4.5:
			break
		lightness -= 0.03
	return colour


def price_row(
	draw, x: int, y: int, detail: dict, price_font, compare_font, badge_font, muted, max_width: int
):
	"""The price, the compare-at price and the saving.

	The price is the largest thing on the card after the photograph, and
	plain bold black rather than a label, so it reads at a glance while
	scrolling. The compare-at price and the saving are set against the
	price's own baseline, so they sit on its line rather than floating
	beside it.
	"""
	price = detail["price"]
	compare = detail.get("compare_at")
	badge = f"SAVE {detail['discount']}%" if detail.get("discount") else ""

	box = draw.textbbox((x, y), price, font=price_font)
	baseline = box[3]
	height = box[3] - box[1]
	middle = (box[1] + box[3]) / 2

	price_width = box[2] - box[0]
	compare_width = text_width(draw, compare, compare_font) if compare else 0
	badge_width = (
		tracked_width(draw, badge, badge_font, 2.0) + int(badge_font.size * 0.9) * 2 if badge else 0
	)
	total = price_width + (18 + compare_width if compare else 0) + (18 + badge_width if badge else 0)

	draw.text((x, baseline), price, font=price_font, fill=INK, anchor="ls")
	offset = x + price_width

	if total <= max_width:
		# All of it on one line, which is where the eye expects it.
		if compare:
			compare_box = draw.textbbox((offset + 18, baseline), compare, font=compare_font, anchor="ls")
			draw.text((offset + 18, baseline), compare, font=compare_font, fill=muted, anchor="ls")
			mid = (compare_box[1] + compare_box[3]) / 2
			draw.line(
				(compare_box[0], mid, compare_box[2], mid), fill=muted, width=3
			)
			offset += 18 + compare_width
		if badge:
			pill = int(badge_font.size * 1.9)
			discount_flag(draw, offset + 18, int(middle - pill / 2), badge, badge_font)
		return height

	# Too wide for the card: the saving goes on a line of its own.
	second_baseline = baseline + 16
	offset = x
	if compare:
		compare_box = draw.textbbox((offset, second_baseline), compare, font=compare_font, anchor="ls")
		draw.text((offset, second_baseline), compare, font=compare_font, fill=muted, anchor="ls")
		mid = (compare_box[1] + compare_box[3]) / 2
		draw.line((compare_box[0], mid, compare_box[2], mid), fill=muted, width=3)
		offset += compare_width + 18
	if badge:
		pill = int(badge_font.size * 1.9)
		compare_mid = middle + 16
		discount_flag(draw, offset, int(compare_mid - pill / 2), badge, badge_font)
	return height + 16 + pill


def price_row_height(detail: dict, price_font, compare_font, badge_font, max_width: int) -> int:
	"""The height the price row takes.

	Measured by drawing it and looking at what it covered, rather than
	assumed - the row is either one line or two depending on how long the
	price is, and the words below it have to land under it either way.
	"""
	scratch = Image.new("RGBA", (max_width + 600, 500), (0, 0, 0, 0))
	price_row(
		ImageDraw.Draw(scratch),
		0,
		0,
		detail,
		price_font,
		compare_font,
		badge_font,
		MUTED,
		max_width,
	)
	box = scratch.getbbox()
	return (box[3] - box[1]) if box else 0


def option_rows(draw, x: int, y: int, detail: dict, layout, width: int) -> int:
	"""The sizes and the colours the product comes in.

	Only what the product actually has: a product that comes in one size
	and no colours says neither.
	"""
	label_font = font("mono", layout["label"], 500)
	option_font = font("display", layout["option"], 500)
	used = 0

	if detail.get("sizes"):
		draw_tracked(draw, (x, y), "SIZE", label_font, MUTED, 3.0)
		used += layout["label"] + 14
		row_y = y + used
		offset = x
		for value in detail["sizes"][:8]:
			draw.text((offset, row_y), value, font=option_font, fill=MUTED)
			offset += text_width(draw, value, option_font) + 22
		used += layout["option"] + 18

	if detail.get("colours"):
		draw_tracked(draw, (x, y + used), "COLOURS", label_font, MUTED, 3.0)
		used += layout["label"] + 14
		row_y = y + used
		offset = x
		size = layout["swatch"]
		for value in detail["colours"][:6]:
			colour = swatch_colour(value)
			draw.ellipse(
				(offset, row_y, offset + size, row_y + size),
				fill=colour,
				outline=HAIRLINE,
				width=2,
			)
			offset += size + 20
		used += size + 6

	return used


def product_card(detail: dict, photo, box, channel: str, full: bool = True) -> Image.Image:
	"""One card: a white card on the ground, a coloured bar, the photograph.

	``full`` is the card that introduces the product - the description, the
	price, the sizes and the colours as well. The others are the pictures.
	"""
	layout = LAYOUTS[channel]
	width, height = CHANNELS[channel]["size"]
	margin = layout["margin"]
	pad = layout["pad"]
	canvas = background_for(detail["tint"], (width, height)).convert("RGBA")
	draw = ImageDraw.Draw(canvas)

	# The white card the template is drawn on.
	card_x = margin
	card_y = margin
	card_w = width - margin * 2
	card_h = height - margin * 2
	radius = 30

	# A soft shadow under it, so it sits on the ground rather than floating.
	shadow_margin = 44
	scale = 4
	small_w = max(1, (card_w + shadow_margin * 2) // scale)
	small_h = max(1, (card_h + shadow_margin * 2) // scale)
	layer = Image.new("RGBA", (small_w, small_h), (0, 0, 0, 0))
	ImageDraw.Draw(layer).rounded_rectangle(
		(
			shadow_margin // scale,
			shadow_margin // scale,
			small_w - shadow_margin // scale,
			small_h - shadow_margin // scale,
		),
		radius=max(1, radius // scale),
		fill=(11, 11, 12, 46),
	)
	layer = layer.filter(ImageFilter.BoxBlur(radius=8))
	layer = layer.resize((card_w + shadow_margin * 2, card_h + shadow_margin * 2), Image.BICUBIC)
	canvas.alpha_composite(layer, (card_x - shadow_margin, card_y + 16 - shadow_margin))
	ImageDraw.Draw(canvas).rounded_rectangle(
		(card_x, card_y, card_x + card_w, card_y + card_h), radius=radius, fill=(255, 255, 255)
	)

	content_x = card_x + pad
	content_w = card_w - pad * 2

	title_font = font("display", layout["title"], 700)
	body_font = font("display", layout["body"], 300)
	price_font = font("display", layout["price"], 700)
	compare_font = font("mono", layout["compare"], 400)
	badge_font = font("mono", round(layout["compare"] * 0.9), 500)

	# The bar at the head of the card, in the product's own colour, with the
	# name in it. The card's rounded corners are the bar's top corners.
	heading = detail["name"]
	heading_lines = wrap_all(draw, heading.upper(), title_font, content_w)
	heading_height = len(heading_lines) * layout["title_line"]
	bar_height = heading_height + 46
	bar = Image.new("RGBA", (card_w, bar_height), (0, 0, 0, 0))
	bar_draw = ImageDraw.Draw(bar)
	bar_draw.rounded_rectangle((0, 0, card_w, bar_height), radius=radius, fill=header_colour(detail["tint"]))
	bar_draw.rectangle((0, bar_height // 2, card_w, bar_height), fill=header_colour(detail["tint"]))
	canvas.alpha_composite(bar, (card_x, card_y))
	text_y = card_y + 23
	for line in heading_lines:
		line_width = text_width(draw, line, title_font)
		draw.text(((width - line_width) / 2, text_y), line, font=title_font, fill=PAPER)
		text_y += layout["title_line"]

	y = card_y + bar_height + layout["gap"]

	# The words below the photograph, and the room they take. Only what is
	# actually there: a product with no colours does not leave room for a
	# row of swatches it does not have.
	price_height = price_row_height(detail, price_font, compare_font, badge_font, content_w) + 30
	options_height = 0
	if detail.get("sizes"):
		options_height += layout["label"] + 14 + layout["option"] + 18
	if detail.get("colours"):
		options_height += layout["label"] + 14 + layout["swatch"] + 6

	logo = store_logo(layout["logo"])
	logo_space = (logo.height + 30) if logo else 0

	# The room the whole group has: the description, the photograph and the
	# words under it.
	bar_bottom = card_y + bar_height
	group_room = card_y + card_h - pad - logo_space - bar_bottom - layout["gap"]

	# The photograph keeps its own shape - it is shown as it was taken -
	# and the words below it are placed against that, so the card looks
	# the same whether the picture is square or four by three.
	picture = None
	picture_width = content_w
	picture_height = 0
	if photo is None:
		# No photograph: a soft panel where it would have gone, so the card
		# is a card and not a hole with words round it.
		picture_height = max(
			240,
			min(
				content_w,
				group_room - price_height - options_height - layout["gap"] * 2,
			),
		)
		picture_width = content_w
	if photo is not None:
		scale = content_w / photo.width
		picture_height = round(photo.height * scale)
		if picture_height > group_room - price_height - options_height - layout["gap"] * 2:
			scale = max(
				0.1,
				(group_room - price_height - options_height - layout["gap"] * 2) / photo.height,
			)
			picture_height = round(photo.height * scale)
		picture_width = round(photo.width * scale)
		picture = photo.convert("RGB").resize((picture_width, picture_height), Image.LANCZOS)

	# The description, small and grey, under the bar.
	description_height = 0
	if full and detail.get("description"):
		body_lines = wrap(draw, detail["description"], body_font, content_w, 2)
		description_height = len(body_lines) * layout["body_line"] + layout["gap"]

	group_height = (
		description_height
		+ picture_height
		+ layout["gap"]
		+ price_height
		+ options_height
	)
	# The group sits in the middle of what is left, so the space it does
	# not fill is shared above and below rather than all of it pooling at
	# the foot of the card.
	group_top = bar_bottom + layout["gap"] + max(0, (group_room - group_height) // 2)

	y = group_top
	if description_height:
		body_lines = wrap(draw, detail["description"], body_font, content_w, 2)
		for line in body_lines:
			line_width = text_width(draw, line, body_font)
			draw.text(((width - line_width) / 2, y), line, font=body_font, fill=MUTED)
			y += layout["body_line"]
		y += layout["gap"]

	photo_top = y
	if picture is not None:
		paste_rounded(
			canvas,
			picture,
			((width - picture_width) // 2, photo_top, picture_width, picture_height),
			radius=18,
		)
	else:
		placeholder = Image.new("RGBA", (picture_width, picture_height), (0, 0, 0, 0))
		ImageDraw.Draw(placeholder).rounded_rectangle(
			(0, 0, picture_width - 1, picture_height - 1),
			radius=18,
			fill=(243, 243, 245, 255),
		)
		canvas.alpha_composite(
			placeholder, ((width - picture_width) // 2, photo_top)
		)
	y = photo_top + picture_height + layout["gap"]

	# The price is on every card. A card is often posted on its own, and a
	# card with a product in it and no price on it is a card nobody can act
	# on.
	price_row(
		draw,
		content_x,
		y,
		detail,
		price_font,
		compare_font,
		badge_font,
		MUTED,
		content_w,
	)
	y += price_height

	# The sizes and the colours are on every card, so a frame that is
	# posted on its own still says what the product comes in.
	option_rows(draw, content_x, y, detail, layout, content_w)

	# The shop's mark, at the foot of the card. On the right, so it ends
	# the line the words are set on rather than sitting beside them.
	if logo:
		canvas.alpha_composite(
			logo,
			(card_x + card_w - pad - logo.width, card_y + card_h - pad - logo.height),
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

	# The sizes and the colours the product comes in, and the collection
	# it belongs to, which is what the cards of the other photographs are
	# headed with.
	from shop.api.variants import product_options
	from shop.storefront.product import product_collections

	sizes: list[str] = []
	colours: list[str] = []
	for option in product_options(doc):
		attribute = (option.get("attribute") or "").strip().lower()
		if attribute == "size":
			sizes = option.get("values") or []
		elif attribute in ("colour", "color"):
			colours = option.get("values") or []
	collections = product_collections(doc)
	collection = collections[0]["title"] if collections else ""

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
		"sizes": sizes,
		"colours": colours,
		"collection": collection,
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
	if not photos:
		# The product lists photographs whose files are not on disk. There is
		# still a card to make - a card with a hole where the picture goes
		# is better than no card at all.
		photos = [(None, None)]
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
				product_card(detail, photo, box, channel, full=first),
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
			"instagram/  1080 x 1350, one card per photograph. The first carries",
			"            the name, the description, the price, the sizes and the",
			"            colours; the rest are the pictures.",
			"tiktok/     1080 x 1920, the same set in a vertical frame.",
			"",
			"The bar at the head of each card is in the product's own colour.",
			"The description goes in the caption of the post, so it is only on the",
			"first card.",
			"",
		]
		if doc.slug:
			readme.append(f"Product: {SITE_BASE}/product/{doc.slug}")
			readme.append("")
		archive.writestr("social-cards/README.txt", "\n".join(readme))
	return buffer.getvalue()
