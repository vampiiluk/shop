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
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request

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


def _await_batch(cfg: dict, handle: str, errors: list[str], warnings: list[str]) -> None:
	"""Poll a batch until it finishes, collecting per-item errors/warnings."""
	query = urllib.parse.urlencode({"handle": handle, "access_token": cfg["token"]})
	for _ in range(STATUS_ATTEMPTS):
		result = _graph(
			"GET", f"{GRAPH_BASE}/{cfg['catalog_id']}/check_batch_request_status?{query}"
		)
		row = (result.get("data") or [{}])[0]
		if row.get("status") == "finished":
			errors.extend(_issue_text(item) for item in row.get("errors") or [])
			warnings.extend(_issue_text(item) for item in row.get("warnings") or [])
			return
		time.sleep(STATUS_INTERVAL)
	warnings.append("Meta batch still processing after waiting; check Commerce Manager")


def _run_requests(cfg: dict, requests: list[dict], errors: list[str], warnings: list[str]) -> int:
	"""Chunk requests into batches, send them, wait for each; returns sent count."""
	sent = 0
	for start in range(0, len(requests), BATCH_LIMIT):
		chunk = requests[start : start + BATCH_LIMIT]
		handles = _post_batch(cfg, chunk)
		sent += len(chunk)
		if not handles:
			warnings.append("Meta returned no status handle for a batch")
		for handle in handles:
			_await_batch(cfg, handle, errors, warnings)
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
			"item",
			"has_variants",
		],
		order_by="name",
	)


def _context(rows: list) -> dict:
	"""Lookups shared by one batch: prices, images, variants and stock."""
	from shop.storefront import catalog, stock

	templates = [row.item for row in rows if row.has_variants]
	variants = catalog.variants_by_template(templates)
	codes = [row.item for row in rows if not row.has_variants]
	for template_codes in variants.values():
		codes.extend(template_codes)
	return {
		"prices": catalog.display_prices(rows),
		"images": catalog.first_images([row.name for row in rows]),
		"variants": variants,
		"qtys": stock.get_stock(codes),
	}


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
		"condition": "new",
		"brand": settings.store_name or "Store",
		"link": f"{SITE_BASE}/product/{product.slug}",
	}
	description = product.description or product.short_description or ""
	if description:
		data["description"] = description[:DESCRIPTION_LIMIT]
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


def _push_rows(rows: list, cfg: dict, settings) -> tuple[int, list[str], list[str]]:
	"""UPDATE (upsert) every row; returns (sent, errors, warnings)."""
	if not rows:
		return 0, [], []
	ctx = _context(rows)
	requests = [
		{"method": "UPDATE", "data": build_item(row, settings, cfg, ctx)} for row in rows
	]
	errors: list[str] = []
	warnings: list[str] = []
	sent = _run_requests(cfg, requests, errors, warnings)
	return sent, errors, warnings


def _fetch_retailer_ids(cfg: dict) -> dict[str, str]:
	"""retailer_id (slug) → Meta product id across the whole catalogue."""
	url = f"{GRAPH_BASE}/{cfg['catalog_id']}/products"
	query = urllib.parse.urlencode(
		{"fields": "id,retailer_id", "limit": "500", "access_token": cfg["token"]}
	)
	ids: dict[str, str] = {}
	for _ in range(40):
		# paging.next is a full URL that already carries its query string (and
		# the access token) — appending a second "?" to it makes Meta reject
		# the request with "Invalid cursor provided", so only add one for the
		# first, hand-built URL.
		result = _graph("GET", f"{url}?{query}" if query else url)
		for row in result.get("data") or []:
			if row.get("retailer_id"):
				ids[row["retailer_id"]] = row["id"]
		next_url = (result.get("paging") or {}).get("next")
		if not next_url:
			break
		url, query = next_url, ""
	return ids


def _link_ids(catalog_ids: dict[str, str]) -> int:
	"""Store each product's Meta id; clear it when the item is no longer listed."""
	linked = 0
	rows = frappe.get_all(
		"Shop Product", fields=["name", "slug", "meta_product_id"]
	)
	for row in rows:
		want = catalog_ids.get(row.slug) or ""
		current = row.meta_product_id or ""
		if want == current:
			continue
		frappe.db.set_value(
			"Shop Product", row.name, "meta_product_id", want or None, update_modified=False
		)
		if want:
			linked += 1
	return linked


def _status_text(pushed: int, deleted: int, linked: int, errors: list[str], warnings: list[str]) -> str:
	"""One-line outcome for the Settings page (Small Text, so capped at 240)."""
	parts = []
	if pushed:
		parts.append(f"Synced {pushed} product{'s' if pushed != 1 else ''}")
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


def _sync(rows: list, cfg: dict, settings, prune: bool = False) -> dict:
	"""Push rows, optionally prune unpublished entries, refresh Meta ids.

	Prune and relink both work off one catalogue listing: entries whose slug
	matches an unpublished Shop Product are deleted (entries that do not match
	any product — added by hand in Commerce Manager — are left alone), and
	every product's ``meta_product_id`` is then set or cleared from that list.
	"""
	errors: list[str] = []
	warnings: list[str] = []

	pushed, push_errors, push_warnings = _push_rows(rows, cfg, settings)
	errors.extend(push_errors)
	warnings.extend(push_warnings)

	deleted = 0
	linked = 0
	catalog_ids: dict[str, str] | None = None
	if rows or prune:
		try:
			catalog_ids = _fetch_retailer_ids(cfg)
		except MetaAPIError as exc:
			warnings.append(f"could not list catalogue items: {exc}")

	if prune and catalog_ids is not None:
		unpublished = set(
			frappe.get_all("Shop Product", filters={"published": 0}, pluck="slug")
		)
		stale = sorted(slug for slug in catalog_ids if slug in unpublished)
		if stale:
			deleted, prune_errors, prune_warnings = _run_requests(
				cfg,
				[{"method": "DELETE", "data": {"id": slug}} for slug in stale],
				[],
				[],
			)
			errors.extend(prune_errors)
			warnings.extend(prune_warnings)
			if not prune_errors:
				for slug in stale:
					catalog_ids.pop(slug, None)

	if catalog_ids is not None:
		linked = _link_ids(catalog_ids)

	status = _status_text(pushed, deleted, linked, errors, warnings)
	_record(status)
	if errors:
		frappe.log_error(
			title="Meta catalog sync failed",
			message="Meta catalog sync reported errors:\n" + "\n".join(errors),
		)
	return {
		"success": not errors,
		"status": status,
		"pushed": pushed,
		"deleted": deleted,
		"linked": linked,
		"errors": errors,
		"warnings": warnings,
	}


def sync_all() -> dict:
	"""Full catalogue sync: push published products, prune, relink ids."""
	cfg = config()
	if not cfg:
		frappe.throw(_("Set the Meta Catalog ID and API key in Shop Settings first."))
	return _sync(_rows(), cfg, frappe.get_doc("Shop Settings"), prune=True)


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
	"""Enqueued on unpublish/trash: DELETE the product from the catalogue."""
	if not active():
		return {"success": False, "status": "Meta catalog sync is off"}
	cfg = config()
	errors: list[str] = []
	warnings: list[str] = []
	_run_requests(cfg, [{"method": "DELETE", "data": {"id": slug}}], errors, warnings)
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
	status = f"Removed {slug} from the catalogue"
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
