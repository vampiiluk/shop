"""Meta (Facebook / WhatsApp) Commerce catalogue sync.

Pushes Shop Products into a Meta catalogue so they show up in WhatsApp and
Facebook, and keeps price and stock in step: a product at zero stock is pushed
as ``out of stock`` with quantity 0, which is what makes WhatsApp stop offering
it. Every pushed product is linked back to its Meta product id
(``Shop Product.meta_product_id``) so the admin editor can point at it.

Graph API v26.0, verified against the live catalogue 1805695184000731:

* ``POST /{catalog}/items_batch`` takes a JSON body
  ``{requests, allow_upsert, item_type: "PRODUCT_ITEM", access_token}`` and
  answers with ``{handles: [...]}``.
* ``GET /{catalog}/check_batch_request_status?handle=…`` reports each batch as
  ``status: "finished"`` plus per-request ``errors``/``warnings``.
* ``GET /{catalog}/products?fields=id,retailer_id`` pages through
  ``paging.next``; ``retailer_id`` is the slug we send as the item ``id``.

Updates merge (a partial UPDATE leaves ``link``/``image_link`` intact),
``quantity_to_sell_on_facebook: 0`` is accepted alongside
``availability: "out of stock"``, and prices normalise to ``PKR1,499.00``.
Descriptions are pushed as plain text: Meta renders them literally, so the
storefront's rich-HTML copy is converted first (``_plain_text``).

Variants and condition, both verified against the live catalogue:

* A product with versions is pushed as a Meta product group: one item per
  variant (id ``{slug}--{item code}``) all sharing ``item_group_id = slug``,
  each carrying its own ``size``/``color``, price, stock and availability.
  Meta builds the "parent" virtually — a plain row whose id equals a group id
  is not allowed — so once a product has variants its old single-item row is
  deleted, along with variant items for versions that no longer exist.
  ``item_group_id`` is written under that name but reads back from the
  products edge as ``retailer_product_group_id``.
* The product's free-text ``condition`` (New, Preloved, whatever the admin
  writes) is normalised to Meta's enum: ``new``, ``refurbished``, ``used``.
"""

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from html import unescape

import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime

GRAPH_BASE = "https://graph.facebook.com/v26.0"
# frappe.utils.get_url() wrongly reports http://…:8000 behind this proxy, so
# absolute storefront links (product pages, images) use this constant instead.
SITE_BASE = "https://erp.sananahmad.dpdns.org"
BATCH_LIMIT = 500
# A 12-item batch already needs more than 10s to flip to "finished".
STATUS_ATTEMPTS = 15
STATUS_INTERVAL = 2
TITLE_LIMIT = 150
DESCRIPTION_LIMIT = 5000


class MetaAPIError(Exception):
	"""The Graph API rejected a request (auth, parameters or network)."""


def config() -> dict | None:
	"""Catalogue credentials from Shop Settings, or None when not set up."""
	settings = frappe.get_doc("Shop Settings")
	catalog_id = (settings.get("meta_catalog_id") or "").strip()
	if not catalog_id:
		return None
	try:
		token = settings.get_password("meta_access_token", raise_exception=False)
	except Exception:
		token = None
	if not token:
		return None
	return {
		"catalog_id": catalog_id,
		"token": token,
		"google_category": (settings.get("meta_google_product_category") or "").strip(),
	}


def active() -> bool:
	"""True when sync is switched on and credentials are present."""
	return bool(cint(frappe.db.get_single_value("Shop Settings", "meta_enabled"))) and (
		config() is not None
	)


def _paused() -> bool:
	"""Skip background sync during migrations, installs and tests."""
	return bool(
		getattr(frappe.flags, "in_migrate", False)
		or getattr(frappe.flags, "in_install", False)
		or getattr(frappe.flags, "in_test", False)
	)


PROGRESS_KEY = "shop_meta_sync_progress"
SYNC_STEPS = (
	("read", "Reading products"),
	("push", "Sending items to Meta"),
	("list", "Listing current catalogue"),
	("prune", "Removing outdated items"),
	("link", "Updating product ids"),
)


class SyncProgress:
	"""Live step status for the admin's sync popup, written to Redis.

	The sync request is synchronous and can run for half a minute (Meta needs
	seconds just to flip a batch to ``finished``), so the popup polls
	``get_meta_sync_progress`` while it waits and renders these steps instead
	of a spinner that sits still. ``run_id`` comes from the client: a poll from
	a sync that has not written anything yet — or a leftover payload from an
	earlier run — comes back as the plain pending skeleton, so a stale step
	list can never be shown as this run's progress. A progress hiccup must
	never fail the sync itself, so every write is best-effort."""

	def __init__(self, run_id: str | None = None):
		self.run_id = run_id or ""
		self.steps = [
			{"key": key, "label": label, "state": "pending", "detail": ""}
			for key, label in SYNC_STEPS
		]
		self.done = False
		self.result: dict | None = None
		self.error: str | None = None
		self._save()

	def set(self, key: str, state: str | None = None, detail=None) -> None:
		for step in self.steps:
			if step["key"] == key:
				if state:
					step["state"] = state
				if detail is not None:
					step["detail"] = str(detail)[:200]
		self._save()

	def finish(self, result: dict | None = None, error: str | None = None) -> None:
		if error:
			self.error = str(error)[:500]
			for step in self.steps:
				# the step that was running when it blew up is the culprit
				if step["state"] == "active":
					step["state"] = "error"
		else:
			for step in self.steps:
				if step["state"] != "done":
					step["state"] = "done"
			self.result = result
		self.done = True
		self._save()

	def snapshot(self) -> dict:
		return {
			"run_id": self.run_id,
			"steps": self.steps,
			"done": self.done,
			"result": self.result,
			"error": self.error,
		}

	def _save(self) -> None:
		try:
			frappe.cache().set_value(PROGRESS_KEY, self.snapshot())
		except Exception:
			pass


def progress_snapshot(run_id: str | None = None) -> dict:
	"""Latest progress for the caller's run, or a pending skeleton."""
	skeleton = {
		"run_id": run_id or "",
		"steps": [
			{"key": key, "label": label, "state": "pending", "detail": ""}
			for key, label in SYNC_STEPS
		],
		"done": False,
		"result": None,
		"error": None,
	}
	try:
		payload = frappe.cache().get_value(PROGRESS_KEY)
	except Exception:
		payload = None
	if not isinstance(payload, dict) or (run_id and payload.get("run_id") != run_id):
		return skeleton
	return payload


def _graph(method: str, url: str, payload: dict | None = None) -> dict:
	"""One Graph API call; raises MetaAPIError with Meta's own message."""
	data = json.dumps(payload).encode() if payload is not None else None
	request = urllib.request.Request(
		url, data=data, headers={"Content-Type": "application/json"}, method=method
	)
	try:
		with urllib.request.urlopen(request, timeout=60) as response:
			return json.loads(response.read().decode() or "{}")
	except urllib.error.HTTPError as exc:
		body = exc.read().decode(errors="replace")
		try:
			message = json.loads(body).get("error", {}).get("message", body)
		except Exception:
			message = body
		raise MetaAPIError(f"HTTP {exc.code}: {message}") from exc
	except urllib.error.URLError as exc:
		raise MetaAPIError(str(exc.reason)) from exc


def _post_batch(cfg: dict, requests: list[dict]) -> list[str]:
	"""Send one items_batch request; returns the status handles to poll."""
	result = _graph(
		"POST",
		f"{GRAPH_BASE}/{cfg['catalog_id']}/items_batch",
		{
			"requests": requests,
			"allow_upsert": True,
			"item_type": "PRODUCT_ITEM",
			"access_token": cfg["token"],
		},
	)
	return result.get("handles") or []


def _issue_text(item) -> str:
	"""Human-readable line from one entry of Meta's errors/warnings list."""
	if isinstance(item, str):
		return item
	if isinstance(item, dict):
		error = item.get("error") or item
		if isinstance(error, dict) and error.get("message"):
			return str(error["message"])
		return json.dumps(item)[:300]
	return str(item)


def _await_batch(
	cfg: dict,
	handle: str,
	errors: list[str],
	warnings: list[str],
	progress: SyncProgress | None = None,
	key: str | None = None,
) -> None:
	"""Poll a batch until it finishes, collecting per-item errors/warnings."""
	query = urllib.parse.urlencode({"handle": handle, "access_token": cfg["token"]})
	for attempt in range(1, STATUS_ATTEMPTS + 1):
		result = _graph(
			"GET", f"{GRAPH_BASE}/{cfg['catalog_id']}/check_batch_request_status?{query}"
		)
		row = (result.get("data") or [{}])[0]
		if row.get("status") == "finished":
			errors.extend(_issue_text(item) for item in row.get("errors") or [])
			warnings.extend(_issue_text(item) for item in row.get("warnings") or [])
			return
		if progress and key:
			# written before the sleep so a poll during the wait sees it move
			progress.set(key, "active", f"Meta is processing the batch ({attempt}/{STATUS_ATTEMPTS})")
		time.sleep(STATUS_INTERVAL)
	warnings.append("Meta batch still processing after waiting; check Commerce Manager")


def _run_requests(
	cfg: dict,
	requests: list[dict],
	errors: list[str],
	warnings: list[str],
	progress: SyncProgress | None = None,
	key: str | None = None,
) -> int:
	"""Chunk requests into batches, send them, wait for each; returns sent count."""
	sent = 0
	batches = (len(requests) + BATCH_LIMIT - 1) // BATCH_LIMIT
	for start in range(0, len(requests), BATCH_LIMIT):
		chunk = requests[start : start + BATCH_LIMIT]
		if progress and key:
			batch = start // BATCH_LIMIT + 1
			progress.set(
				key,
				"active",
				f"Sending batch {batch} of {batches} ({len(chunk)} items)",
			)
		handles = _post_batch(cfg, chunk)
		sent += len(chunk)
		if not handles:
			warnings.append("Meta returned no status handle for a batch")
		for handle in handles:
			_await_batch(cfg, handle, errors, warnings, progress=progress, key=key)
	return sent


def _absolute(url: str) -> str:
	"""Absolute URL for a stored (usually root-relative) asset path."""
	if not url:
		return ""
	if url.startswith(("http://", "https://")):
		return url
	return SITE_BASE + ("" if url.startswith("/") else "/") + url


def _money(amount: float, currency: str) -> str:
	return f"{flt(amount):.2f} {currency or 'PKR'}"


def _rows(names: list[str] | None = None) -> list:
	"""Published Shop Products to push (optionally limited to these names)."""
	filters: dict = {"published": 1}
	if names:
		filters["name"] = ["in", names]
	return frappe.get_all(
		"Shop Product",
		filters=filters,
		fields=[
			"name",
			"slug",
			"product_name",
			"short_description",
			"description",
			"compare_at_price",
			"condition",
			"item",
			"has_variants",
		],
		order_by="name",
	)


def _context(rows: list) -> dict:
	"""Lookups shared by one batch: prices, images, variants and stock."""
	from shop.storefront import catalog, pricing, stock

	templates = [row.item for row in rows if row.has_variants]
	variants = catalog.variants_by_template(templates)
	codes = [row.item for row in rows if not row.has_variants]
	for template_codes in variants.values():
		codes.extend(template_codes)
	variant_codes = [code for template_codes in variants.values() for code in template_codes]
	return {
		"prices": catalog.display_prices(rows),
		# per-variant rates: variants are their own catalogue items now
		"variant_prices": pricing.get_prices(variant_codes),
		"variant_attrs": _variant_attrs(variant_codes),
		"images": catalog.first_images([row.name for row in rows]),
		"variants": variants,
		"qtys": stock.get_stock(codes),
	}


def _plain_text(value: str) -> str:
	"""Convert the storefront's rich-HTML copy to plain text.

	Meta renders item descriptions literally, so the ``<p>`` markup the rich
	text editor wraps paragraphs in would show up in front of the customer in
	WhatsApp. Paragraph/list/line breaks survive as newlines so the copy stays
	readable rather than running together.
	"""
	text = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
	text = re.sub(r"</(p|div|li|tr|h[1-6])\s*>", "\n", text, flags=re.I)
	text = re.sub(r"<(p|div|ul|ol|tr|h[1-6])\b[^>]*>", "\n", text, flags=re.I)
	text = re.sub(r"<li[^>]*>", "- ", text, flags=re.I)
	text = re.sub(r"<[^>]+>", "", text)
	text = unescape(text)
	text = re.sub(r"[ \t\u00a0]+", " ", text)
	text = re.sub(r" *\n *", "\n", text)
	text = re.sub(r"\n{3,}", "\n\n", text)
	return text.strip()


# ERPNext attribute names that map onto Meta's core variant fields. Anything
# else has no place in an items_batch item (Meta takes custom variants through
# supplementary feeds only) and is skipped.
CORE_VARIANT_FIELDS = {
	"size": "size",
	"colour": "color",
	"color": "color",
	"material": "material",
	"pattern": "pattern",
	"gender": "gender",
	"age": "age_group",
	"age group": "age_group",
}


def _condition(value) -> str:
	"""The admin's free text ("New", "Preloved", …) → Meta's condition enum.

	Meta only accepts ``new``, ``refurbished`` and ``used``. Anything written
	that is not obviously new ("preloved", "second hand", a custom phrase)
	maps to ``used`` — if the admin took the trouble to type a condition,
	it isn't new. Empty stays the current default, ``new``.
	"""
	text = str(value or "").strip().lower()
	if not text:
		return "new"
	# checked first: "renewed" contains "new"
	if any(token in text for token in ("refurb", "renew", "open box", "open-box", "openbox")):
		return "refurbished"
	if "new" in text:
		return "new"
	return "used"


def _child_id(slug: str, code: str) -> str:
	"""Stable catalogue id for one variant; Meta caps ids at 100 chars."""
	child = f"{slug}--{code.lower()}"
	return child if len(child) <= 100 else code.lower()[:100]


def _variant_attrs(codes: list[str]) -> dict[str, dict]:
	"""{item code: {meta field: value}} from ERPNext's item attributes."""
	attrs: dict[str, dict] = {}
	if not codes:
		return attrs
	rows = frappe.get_all(
		"Item Variant Attribute",
		filters={"parent": ["in", codes]},
		fields=["parent", "attribute", "attribute_value"],
		order_by="parent, idx",
	)
	for row in rows:
		field = CORE_VARIANT_FIELDS.get((row.attribute or "").strip().lower())
		value = str(row.attribute_value or "").strip()
		if field and value and field not in attrs.setdefault(row.parent, {}):
			attrs[row.parent][field] = value
	return attrs


def build_item(product, settings, cfg: dict, ctx: dict) -> dict:
	"""One Meta catalogue item mirroring exactly what the storefront shows."""
	variant_codes = ctx["variants"].get(product.item)
	codes = variant_codes or ([] if product.has_variants else [product.item])
	qty = sum(ctx["qtys"].get(code, 0.0) for code in codes)
	if cint(settings.allow_out_of_stock) or not frappe.get_cached_value(
		"Item", product.item, "is_stock_item"
	):
		in_stock = True
	else:
		in_stock = qty > 0

	data = {
		"id": product.slug,
		"title": (product.product_name or product.slug)[:TITLE_LIMIT],
		# Availability + quantity are what WhatsApp keys off: "out of stock"
		# with quantity 0 is what hides a product that has sold out.
		"availability": "in stock" if in_stock else "out of stock",
		"quantity_to_sell_on_facebook": max(int(qty), 1) if in_stock else 0,
		"condition": _condition(product.condition),
		"brand": settings.store_name or "Store",
		"link": f"{SITE_BASE}/product/{product.slug}",
	}
	description = product.description or product.short_description or ""
	if description:
		# Meta shows the description as plain text — the storefront's HTML
		# would put literal <p> tags in front of the customer.
		data["description"] = _plain_text(description)[:DESCRIPTION_LIMIT]
	rate = flt((ctx["prices"].get(product.item) or {}).get("rate"))
	compare_at = flt(product.compare_at_price)
	if rate > 0:
		currency = settings.currency or "PKR"
		if compare_at > rate:
			# Storefront shows compare_at struck through above the sale price.
			data["price"] = _money(compare_at, currency)
			data["sale_price"] = _money(rate, currency)
		else:
			data["price"] = _money(rate, currency)
	image = ctx["images"].get(product.name)
	if image:
		data["image_link"] = _absolute(image)
	if cfg.get("google_category"):
		data["google_product_category"] = cfg["google_category"]
	return data


def build_items(product, settings, cfg: dict, ctx: dict) -> list[dict]:
	"""Every catalogue item for one product.

	Simple products stay the single item they always were. A product with
	variants becomes a Meta product group: one item per variant, all sharing
	``item_group_id`` with the slug and carrying that variant's own size and
	color, price, stock and availability. The group's "parent" is virtual —
	Meta rejects a plain row whose id equals a group id — so the slug row
	only exists while the product has no variants.
	"""
	variant_codes = ctx["variants"].get(product.item) or []
	if not variant_codes:
		return [build_item(product, settings, cfg, ctx)]

	base = build_item(product, settings, cfg, ctx)
	always_available = cint(settings.allow_out_of_stock) or not frappe.get_cached_value(
		"Item", product.item, "is_stock_item"
	)
	compare_at = flt(product.compare_at_price)
	currency = settings.currency or "PKR"
	items = []
	for code in variant_codes:
		qty = ctx["qtys"].get(code, 0.0)
		in_stock = always_available or qty > 0
		child = {
			"id": _child_id(product.slug, code),
			"item_group_id": product.slug,
			# Meta keeps the title stable while the buyer picks a variant,
			# so every member carries the product's own name.
			"title": base["title"],
			"availability": "in stock" if in_stock else "out of stock",
			"quantity_to_sell_on_facebook": max(int(qty), 1) if in_stock else 0,
			"condition": base["condition"],
			"brand": base["brand"],
			"link": base["link"],
		}
		if base.get("description"):
			child["description"] = base["description"]
		# this variant's own rate, falling back to the product's lowest
		rate = flt((ctx["variant_prices"].get(code) or {}).get("rate")) or flt(
			(ctx["prices"].get(product.item) or {}).get("rate")
		)
		if rate > 0:
			if compare_at > rate:
				child["price"] = _money(compare_at, currency)
				child["sale_price"] = _money(rate, currency)
			else:
				child["price"] = _money(rate, currency)
		if base.get("image_link"):
			child["image_link"] = base["image_link"]
		if base.get("google_product_category"):
			child["google_product_category"] = base["google_product_category"]
		child.update(ctx["variant_attrs"].get(code) or {})
		items.append(child)
	return items


def _push_rows(
	rows: list, cfg: dict, settings, ctx: dict, progress: SyncProgress | None = None
) -> tuple[int, int, list[str], list[str]]:
	"""UPDATE (upsert) every item; returns (products, items, errors, warnings)."""
	if not rows:
		return 0, 0, [], []
	if progress:
		progress.set("push", "active", f"Preparing {len(rows)} products")
	requests = [
		{"method": "UPDATE", "data": item}
		for row in rows
		for item in build_items(row, settings, cfg, ctx)
	]
	errors: list[str] = []
	warnings: list[str] = []
	sent = _run_requests(cfg, requests, errors, warnings, progress=progress, key="push")
	return len(rows), sent, errors, warnings


def _fetch_catalog(cfg: dict) -> dict[str, dict]:
	"""retailer_id → {id, group} across the whole catalogue.

	The group is written as ``item_group_id`` but only reads back as
	``retailer_product_group_id`` — the products edge ignores
	``item_group_id`` (verified against the live catalogue).
	"""
	url = f"{GRAPH_BASE}/{cfg['catalog_id']}/products"
	query = urllib.parse.urlencode(
		{
			"fields": "id,retailer_id,retailer_product_group_id",
			"limit": "500",
			"access_token": cfg["token"],
		}
	)
	entries: dict[str, dict] = {}
	for _ in range(40):
		# paging.next is a full URL that already carries its query string (and
		# the access token) — appending a second "?" to it makes Meta reject
		# the request with "Invalid cursor provided", so only add one for the
		# first, hand-built URL.
		result = _graph("GET", f"{url}?{query}" if query else url)
		for row in result.get("data") or []:
			if row.get("retailer_id"):
				entries[row["retailer_id"]] = {
					"id": row["id"],
					"group": row.get("retailer_product_group_id") or "",
				}
		next_url = (result.get("paging") or {}).get("next")
		if not next_url:
			break
		url, query = next_url, ""
	return entries


def _link_ids(catalog: dict[str, dict]) -> int:
	"""Store each product's Meta id; clear it when the item is no longer listed.

	A variant product has no item of its own, so it links to its group's
	first member (sorted, keeping the id stable between syncs) — the
	Commerce Manager search finds that id just as well."""
	linked = 0
	groups: dict[str, list[str]] = {}
	for rid, entry in catalog.items():
		if entry["group"]:
			groups.setdefault(entry["group"], []).append(rid)
	for members in groups.values():
		members.sort()
	rows = frappe.get_all(
		"Shop Product", fields=["name", "slug", "meta_product_id"]
	)
	for row in rows:
		want = (catalog.get(row.slug) or {}).get("id") or ""
		if not want and row.slug in groups:
			want = catalog[groups[row.slug][0]]["id"]
		current = row.meta_product_id or ""
		if want == current:
			continue
		frappe.db.set_value(
			"Shop Product", row.name, "meta_product_id", want or None, update_modified=False
		)
		if want:
			linked += 1
	return linked


def _status_text(
	synced: int,
	deleted: int,
	linked: int,
	errors: list[str],
	warnings: list[str],
	items: int | None = None,
) -> str:
	"""One-line outcome for the Settings page (Small Text, so capped at 240)."""
	parts = []
	if synced:
		line = f"Synced {synced} product{'s' if synced != 1 else ''}"
		if items and items != synced:
			# a variant product expands into one item per variant
			line += f" ({items} items)"
		parts.append(line)
	if deleted:
		parts.append(f"Removed {deleted}")
	if linked:
		parts.append(f"Linked {linked} new id{'s' if linked != 1 else ''}")
	for issue, label in ((errors, "error"), (warnings, "warning")):
		if issue:
			parts.append(f"{len(issue)} {label}{'s' if len(issue) != 1 else ''}")
			parts.append(issue[0])
			break
	if not parts:
		return "Catalogue up to date"
	return " · ".join(parts)[:240]


def _record(status: str) -> None:
	"""Persist the outcome shown on the Settings page."""
	frappe.db.set_single_value("Shop Settings", "meta_last_sync", now_datetime())
	frappe.db.set_single_value("Shop Settings", "meta_sync_status", status)


def _stale_ids(rows: list, catalog: dict[str, dict], ctx: dict, prune: bool, keep_legacy: bool = False) -> list[str]:
	"""Catalogue ids that no longer belong.

	With pruning (a full sync): everything belonging to an unpublished Shop
	Product — its own row and its variant-group members alike. For every
	product just pushed, additionally its old single-item row (now that it
	has variants) and variant items for versions no longer sold. Entries
	that match no product at all — added by hand in Commerce Manager — are
	never touched.
	"""
	stale: set[str] = set()
	if prune:
		unpublished = set(
			frappe.get_all("Shop Product", filters={"published": 0}, pluck="slug")
		)
		for rid, entry in catalog.items():
			if rid in unpublished or (entry["group"] and entry["group"] in unpublished):
				stale.add(rid)
	variants = ctx.get("variants") or {}
	for row in rows:
		codes = variants.get(row.item) or []
		if not codes:
			continue  # simple product: its own row is current
		expected = {_child_id(row.slug, code) for code in codes}
		if row.slug in catalog and not keep_legacy:
			# the pre-variant single-item row; kept when the push errored so
			# a failed batch can't leave the product out of the catalogue
			stale.add(row.slug)
		for rid, entry in catalog.items():
			if entry["group"] == row.slug and rid not in expected:
				stale.add(rid)  # a variant that no longer exists
	return sorted(stale)


def _sync(
	rows: list,
	cfg: dict,
	settings,
	prune: bool = False,
	progress: SyncProgress | None = None,
) -> dict:
	"""Push rows, drop what no longer belongs, refresh Meta ids.

	Prune, group cleanup and relink all work off one catalogue listing (see
	``_stale_ids``); every product's ``meta_product_id`` is then set or
	cleared from that same listing.
	"""
	errors: list[str] = []
	warnings: list[str] = []

	ctx = _context(rows) if rows else {}
	pushed_products, pushed_items, push_errors, push_warnings = _push_rows(
		rows, cfg, settings, ctx, progress=progress
	)
	errors.extend(push_errors)
	warnings.extend(push_warnings)
	if progress:
		progress.set(
			"push",
			"done",
			f"Sent {pushed_items} item{'s' if pushed_items != 1 else ''}"
			if pushed_items
			else "Nothing to send",
		)

	deleted = 0
	linked = 0
	catalog: dict[str, dict] | None = None
	if rows or prune:
		if progress:
			progress.set("list", "active", "Reading the catalogue from Meta")
		try:
			catalog = _fetch_catalog(cfg)
		except MetaAPIError as exc:
			warnings.append(f"could not list catalogue items: {exc}")
		if progress:
			progress.set(
				"list",
				"done" if catalog is not None else "error",
				f"{len(catalog)} items listed" if catalog is not None else "Could not list the catalogue",
			)

	if catalog is not None:
		stale = _stale_ids(rows, catalog, ctx, prune, keep_legacy=bool(push_errors))
		if progress:
			progress.set("prune", "active", f"{len(stale)} outdated item{'s' if len(stale) != 1 else ''}")
		if stale:
			deleted, prune_errors, prune_warnings = _run_requests(
				cfg,
				[{"method": "DELETE", "data": {"id": rid}} for rid in stale],
				[],
				[],
				progress=progress,
				key="prune",
			)
			errors.extend(prune_errors)
			warnings.extend(prune_warnings)
			if not prune_errors:
				for rid in stale:
					catalog.pop(rid, None)
		if progress:
			progress.set(
				"prune",
				"done",
				f"Removed {deleted} item{'s' if deleted != 1 else ''}" if deleted else "Nothing to remove",
			)
		if progress:
			progress.set("link", "active")
		linked = _link_ids(catalog)
		if progress:
			progress.set(
				"link",
				"done",
				f"{linked} product id{'s' if linked != 1 else ''} updated" if linked else "Product ids already current",
			)
	elif progress:
		# the listing failed: prune and relink have nothing to work from
		progress.set("prune", "done", "Skipped — catalogue unavailable")
		progress.set("link", "done", "Skipped — catalogue unavailable")

	status = _status_text(
		pushed_products, deleted, linked, errors, warnings, items=pushed_items
	)
	_record(status)
	if errors:
		frappe.log_error(
			title="Meta catalog sync failed",
			message="Meta catalog sync reported errors:\n" + "\n".join(errors),
		)
	return {
		"success": not errors,
		"status": status,
		"pushed": pushed_items,
		"products": pushed_products,
		"deleted": deleted,
		"linked": linked,
		"errors": errors,
		"warnings": warnings,
	}


def sync_all(run_id: str | None = None) -> dict:
	"""Full catalogue sync: push published products, prune, relink ids.

	``run_id`` is the browser's polling token: with it, every step is written
	to the progress cache for the popup; without it (scheduled and background
	syncs) nothing is written, so a background run can never clobber the steps
	of a manual sync in flight."""
	cfg = config()
	if not cfg:
		frappe.throw(_("Set the Meta Catalog ID and API key in Shop Settings first."))
	progress = SyncProgress(run_id) if run_id else None
	try:
		rows = _rows()
		if progress:
			progress.set(
				"read",
				"done",
				f"{len(rows)} published product{'s' if len(rows) != 1 else ''}",
			)
		result = _sync(
			rows, cfg, frappe.get_doc("Shop Settings"), prune=True, progress=progress
		)
	except Exception as exc:
		if progress:
			progress.finish(error=str(exc))
		raise
	if progress:
		progress.finish(result)
	return result


def push_products(names: list[str]) -> dict:
	"""Enqueued after a product save or stock change: push just those rows."""
	if not active():
		return {"success": False, "status": "Meta catalog sync is off"}
	cfg = config()
	rows = _rows(names)
	if not rows:
		return {"success": True, "status": "Nothing to push"}
	return _sync(rows, cfg, frappe.get_doc("Shop Settings"))


def drop_product(slug: str) -> dict:
	"""Enqueued on unpublish/trash: DELETE the product from the catalogue.

	Removes the product's own row plus every member of its variant group."""
	if not active():
		return {"success": False, "status": "Meta catalog sync is off"}
	cfg = config()
	errors: list[str] = []
	warnings: list[str] = []
	ids = [slug]
	try:
		for rid, entry in _fetch_catalog(cfg).items():
			if entry["group"] == slug and rid not in ids:
				ids.append(rid)
	except MetaAPIError as exc:
		# The product's own row can still go without the listing.
		warnings.append(f"could not list variant items: {exc}")
	_run_requests(
		cfg, [{"method": "DELETE", "data": {"id": rid}} for rid in ids], errors, warnings
	)
	if errors:
		status = _status_text(0, 0, 0, errors, warnings)
		_record(status)
		frappe.log_error(
			title="Meta catalog sync failed",
			message=f"Removing {slug} from the Meta catalogue failed:\n" + "\n".join(errors),
		)
		return {"success": False, "status": status}
	name = frappe.db.get_value("Shop Product", {"slug": slug}, "name")
	if name:
		# The entry is gone: clear the id so a later republish re-links the new one.
		frappe.db.set_value("Shop Product", name, "meta_product_id", None, update_modified=False)
	variants = len(ids) - 1
	status = f"Removed {slug} from the catalogue" + (
		f" with {variants} variant{'s' if variants != 1 else ''}" if variants else ""
	)
	if warnings:
		# e.g. the variant listing failed: the hourly sync retries those
		status = f"{status} · {warnings[0]}"[:240]
	_record(status)
	return {"success": True, "status": status}


def products_for_item(item_code: str) -> list[str]:
	"""Published Shop Products affected by a stock move on this item code."""
	variant_of = frappe.db.get_value("Item", item_code, "variant_of")
	codes = [item_code] + ([variant_of] if variant_of else [])
	return frappe.get_all(
		"Shop Product",
		filters={"item": ["in", codes], "published": 1},
		pluck="name",
	)


def on_product_update(doc, method=None) -> None:
	"""Shop Product saved: push it, or drop it when unpublished."""
	if _paused() or not active():
		return
	if doc.published:
		frappe.enqueue(
			"shop.integrations.meta_catalog.push_products",
			names=[doc.name],
			queue="short",
			enqueue_after_commit=True,
			job_id=f"meta-push-{doc.name}",
			deduplicate=True,
		)
	elif doc.meta_product_id:
		frappe.enqueue(
			"shop.integrations.meta_catalog.drop_product",
			slug=doc.slug,
			queue="short",
			enqueue_after_commit=True,
			job_id=f"meta-drop-{doc.name}",
			deduplicate=True,
		)


def on_product_trash(doc, method=None) -> None:
	"""Shop Product deleted: remove its catalogue entry."""
	if _paused() or not active() or not doc.meta_product_id:
		return
	frappe.enqueue(
		"shop.integrations.meta_catalog.drop_product",
		slug=doc.slug,
		queue="short",
		enqueue_after_commit=True,
		job_id=f"meta-drop-{doc.name}",
		deduplicate=True,
	)


def on_stock_change(doc, method=None) -> None:
	"""Stock Ledger Entry submitted or cancelled: refresh availability."""
	if _paused() or not active():
		return
	names = products_for_item(doc.item_code)
	if not names:
		return
	frappe.enqueue(
		"shop.integrations.meta_catalog.push_products",
		names=names,
		queue="short",
		enqueue_after_commit=True,
		job_id=f"meta-stock-{doc.item_code}",
		deduplicate=True,
	)


def scheduled_reconcile() -> None:
	"""Hourly safety net: push everything, prune stale entries, relink ids."""
	if _paused() or not active():
		return
	try:
		sync_all()
	except Exception:
		frappe.log_error(title="Meta catalog sync failed")
		_record("Sync failed — see Error Log")
