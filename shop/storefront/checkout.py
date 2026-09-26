from contextlib import contextmanager

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import add_days, cint, flt, nowdate, validate_email_address

from shop import payments as raast_module
from shop.storefront import cart as cart_module
from shop.storefront import pickup as pickup_module
from shop.storefront import pricing, stock


def advance_amount_for(total, settings) -> float:
	"""Advance due on an order total: percent of the total or a flat amount, clamped to it."""
	total = flt(total)
	if total <= 0:
		return 0.0
	if (settings.advance_payment_mode or "Percent") == "Flat":
		amount = flt(settings.advance_payment_flat)
	else:
		amount = total * flt(settings.advance_payment_percent or 0) / 100
	return max(0.0, min(amount, total))


def advance_due_for(payment_method, total, settings) -> float:
	"""Advance to record up front for an order placed with this method.

	Advance Payment and Raast QR are one option at checkout — the QR settles
	what is due today and the courier takes the balance — so a Raast order
	carries an advance figure whenever Advance Payment is switched on, and
	that figure is what the QR is drawn for. Orders placed before the merge
	still arrive as "advance" and keep theirs; every other method pays
	nothing up front.
	"""
	if payment_method == "advance":
		return advance_amount_for(total, settings)
	if payment_method == "raast" and cint(settings.enable_advance_payment):
		return advance_amount_for(total, settings)
	return 0.0


@frappe.whitelist(allow_guest=True)
def get_checkout_summary() -> dict:
	cart = cart_module.resolve_cart()
	settings = frappe.get_cached_doc("Shop Settings")
	payload = cart_module.cart_payload(cart)
	methods = []
	if settings.enable_cod:
		methods.append({"method": "cod", "label": _("Cash on Delivery")})
	if settings.payment_gateway_account:
		methods.append({"method": "gateway", "label": _("Pay Online")})
	total = flt(payload.get("total"))
	# Advance Payment and Raast QR were two rows asking for the same IBAN and
	# the same transfer, so they are one row now: the QR settles what is due
	# today — the advance when Advance Payment is switched on, the whole total
	# when it is not — and the courier collects any balance on delivery, which
	# is exactly what the advance basis and percent already decide. The plain
	# Advance row survives only where there is no QR to show for it.
	advance_on = bool(cint(settings.enable_advance_payment)) and total > 0
	advance = advance_amount_for(total, settings) if advance_on else 0.0
	balance = max(total - advance, 0.0)
	if raast_module.configured(settings) and total > 0:
		if advance > 0 and balance > 0:
			label = _("Advance Payment — {0} now by QR · {1} on delivery").format(
				pricing.format_amount(advance), pricing.format_amount(balance)
			)
		else:
			label = _("Advance Payment — pay {0} in full now").format(pricing.format_amount(total))
		methods.append(
			{
				"method": "raast",
				"label": label,
				"advance_amount": advance,
				"balance_amount": balance,
			}
		)
	elif advance_on:
		formatted_advance = pricing.format_amount(advance)
		if balance > 0:
			label = _("Advance Payment — {0} now · {1} on delivery").format(
				formatted_advance, pricing.format_amount(balance)
			)
		else:
			label = _("Advance Payment — pay {0} in full now").format(formatted_advance)
		methods.append(
			{
				"method": "advance",
				"label": label,
				"advance_amount": advance,
				"balance_amount": balance,
			}
		)
	pickup_locations = pickup_module.configured(settings)
	if pickup_locations:
		methods.append({"method": "pickup", "label": _("Store Pickup — pay when you collect")})
	return {
		"cart": payload,
		"payment_methods": methods,
		"currency": settings.currency,
		"prefill": checkout_prefill(),
		"addresses": saved_addresses(),
		"has_addresses": "true" if saved_addresses_exist() else None,
		"pickup_locations": pickup_locations or None,
		# Location auto-checked when Store Pickup is chosen (data-default on
		# the panel); '' means "let the customer pick one".
		"default_pickup_location": (settings.get("default_pickup_location") or "").strip(),
		# Totals shown while pickup is selected: no courier, so no shipping fee.
		"pickup_view": {
			"formatted_shipping": _("Free"),
			"formatted_total": pricing.format_amount(flt(payload.get("total")) - flt(payload.get("shipping"))),
		}
		if pickup_locations
		else None,
	}


PREFILL_FIELDS = (
	"email",
	"full_name",
	"phone",
	"address_line1",
	"address_line2",
	"city",
	"state",
	"country",
	"pincode",
	"landmark",
	"alt_phone",
)


def checkout_prefill() -> dict:
	"""Signed-in customers get their details back instead of an empty form."""
	prefill = dict.fromkeys(PREFILL_FIELDS, "")
	user = frappe.session.user
	if user in ("Guest", None, "Administrator"):
		prefill["country"] = frappe.db.get_default("country") or ""
		return prefill
	prefill["email"] = user
	prefill["full_name"] = frappe.db.get_value("User", user, "full_name") or ""
	from shop.storefront.orders import session_customers

	customers = session_customers()
	if not customers:
		prefill["country"] = frappe.db.get_default("country") or ""
		return prefill
	prefill["phone"] = contact_phone(user) or ""
	address = last_shipping_address(customers)
	for field, value in (address or {}).items():
		prefill[field] = value or ""
	if not prefill["phone"]:
		prefill["phone"] = address.get("phone", "") if address else ""
	if not prefill["country"]:
		prefill["country"] = frappe.db.get_default("country") or ""
	return prefill


def contact_phone(user: str) -> str | None:
	contact = frappe.db.get_value("Contact Email", {"email_id": user}, "parent")
	if not contact:
		return None
	return frappe.db.get_value("Contact", contact, "mobile_no") or frappe.db.get_value(
		"Contact", contact, "phone"
	)


ADDRESS_FIELDS = ("address_line1", "address_line2", "city", "state", "country", "pincode", "custom_landmark", "custom_alt_phone")


def saved_addresses_exist() -> bool:
	return len(saved_addresses()) > 1


def saved_addresses() -> list[dict]:
	"""Every address this customer has shipped to, newest first, plus a blank entry."""
	from shop.storefront.orders import session_customers

	if frappe.session.user in ("Guest", None, "Administrator"):
		return []
	customers = session_customers()
	if not customers:
		return []
	links = frappe.get_all(
		"Dynamic Link",
		filters={"parenttype": "Address", "link_doctype": "Customer", "link_name": ["in", customers]},
		pluck="parent",
	)
	if not links:
		return []
	rows = frappe.get_all(
		"Address",
		filters={"name": ["in", links]},
		fields=["name", *ADDRESS_FIELDS],
		order_by="modified desc",
		limit=6,
	)
	for row in rows:
		row.landmark = row.custom_landmark or ""
		row.alt_phone = row.custom_alt_phone or ""
		row.line = ", ".join(str(row[field]) for field in ("address_line1", "city", "pincode") if row.get(field))
	rows.append(frappe._dict({"name": "", "line": _("Enter a new address")}))
	return rows


def last_shipping_address(customers: list[str]) -> dict | None:
	links = frappe.get_all(
		"Dynamic Link",
		filters={"parenttype": "Address", "link_doctype": "Customer", "link_name": ["in", customers]},
		pluck="parent",
	)
	if not links:
		return None
	rows = frappe.get_all(
		"Address",
		filters={"name": ["in", links]},
		fields=["address_line1", "address_line2", "city", "state", "country", "pincode", "custom_landmark", "custom_alt_phone"],
		order_by="modified desc",
		limit=1,
	)
	if not rows:
		return None
	row = rows[0]
	return {
		"address_line1": row.address_line1,
		"address_line2": row.address_line2,
		"city": row.city,
		"state": row.state,
		"country": row.country,
		"pincode": row.pincode,
		"landmark": row.custom_landmark,
		"alt_phone": row.custom_alt_phone,
	}


def _get_client_ip() -> str:
	"""Extract the real client IP from the current request."""
	try:
		ip = frappe.request.headers.get("CF-Connecting-IP") or frappe.request.headers.get("X-Forwarded-For") or ""
		if not ip and frappe.request:
			ip = getattr(frappe.request, "remote_addr", "") or ""
		# CF-Connecting-IP is the first IP; X-Forwarded-For may have commas
		ip = (ip.split(",")[0]).strip() if ip else ""
		return ip
	except Exception:
		return ""


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=30, seconds=60)
def place_order(customer: dict, address: dict, payment_method: str = "cod", device_fingerprint: str = "", fp_request_id: str = "", fingerprint_provider: str = "", fp_signals: str = "", pickup_location: str = "") -> dict:
	cart = cart_module.resolve_cart()
	validate_order(cart, customer, address, payment_method, pickup_location)
	settings = frappe.get_cached_doc("Shop Settings")
	client_ip = _get_client_ip()
	from shop.integrations import fraud as fraud_module

	fraud = None
	if cint(frappe.db.get_single_value("Shop Settings", "enable_fraud_check")):
		fraud = fraud_module.fast_risk(customer, address, payment_method, device_fingerprint or "")
		if fraud.verdict == "Block":
			fraud_module.log_fraud_event(None, customer, address, payment_method, device_fingerprint or "", fraud)
			if payment_method == "pickup":
				frappe.throw(_("This order could not be placed for store pickup. Please pay online or contact us."))
			frappe.throw(_("This order could not be placed with Cash on Delivery. Please pay online or contact us."))
	with elevated():
		party = get_or_create_customer(customer)
		if device_fingerprint:
			frappe.db.set_value("Customer", party, "custom_device_fingerprint", device_fingerprint)
		shipping_address = create_address(party, customer, address)
		# Recorded for the merged Raast option as well as the old advance one:
		# it is the figure the QR is drawn for and the one the courier is
		# short of on delivery.
		advance_amount = advance_due_for(
			payment_method, cart_module.cart_payload(cart)["total"], settings
		)
		sales_order = create_sales_order(
			cart,
			party,
			shipping_address,
			device_fingerprint,
			customer,
			fingerprint_provider,
			payment_method=payment_method,
			advance_amount=advance_amount,
			pickup_location=pickup_location if payment_method == "pickup" else "",
		)
		# Store client IP for fraud intel
		if client_ip:
			frappe.db.set_value("Sales Order", sales_order.name, "custom_client_ip", client_ip)
		# Store raw browser signals from fingerprint provider
		if fp_signals:
			frappe.db.set_value("Sales Order", sales_order.name, "custom_fp_event", fp_signals)
		# stamp initial fast_risk verdict immediately
		if fraud:
			fraud_module.stamp_order(sales_order.name, device_fingerprint or "", fp_request_id or "", fraud, fingerprint_provider)
			fraud_module.log_fraud_event(sales_order.name, customer, address, payment_method, device_fingerprint or "", fraud)
		convert_cart(cart, sales_order)
		confirmation_url = f"/order-confirmation/{sales_order.name}?token={cart.token}"
		queue_confirmation_email(sales_order, customer["email"], confirmation_url)
		response = {
			"sales_order": sales_order.name,
			"confirmation_url": confirmation_url,
		}
		# enqueue full fraud evaluation (geocode + fingerprint) as background job
		if cint(frappe.db.get_single_value("Shop Settings", "enable_fraud_check")):
			frappe.enqueue(
				"shop.integrations.fraud.background_fraud_task",
				queue="default",
				order_name=sales_order.name,
				customer=customer,
				address=address,
				payment_method=payment_method,
				device_fingerprint=device_fingerprint or "",
				fp_request_id=fp_request_id or "",
				ip_address=client_ip,
			)
		if payment_method == "gateway" or (fraud and fraud.verdict == "Advance Required"):
			# Raast is settled by scanning a QR on the confirmation page: it has
			# no gateway to redirect to, and the customer is paying the whole
			# order up front, so the order stands as placed either way.
			if payment_method == "raast":
				if fraud:
					fraud.signals["advance_deferred"] = True
					fraud_module.stamp_order(sales_order.name, device_fingerprint or "", fp_request_id or "", fraud, fingerprint_provider)
			elif settings and not settings.payment_gateway_account and payment_method in (
				"cod",
				"pickup",
				"advance",
			):
				# no way to take payment yet: allow the order, keep the flag visible
				if fraud:
					fraud.signals["advance_deferred"] = True
					fraud_module.stamp_order(sales_order.name, device_fingerprint or "", fp_request_id or "", fraud, fingerprint_provider)
			else:
				response["payment_url"] = create_payment_request(sales_order, customer)
				if fraud and fraud.verdict == "Advance Required":
					response["payment_required"] = True
	return response


def queue_confirmation_email(sales_order, email: str, confirmation_url: str):
	try:
		message, inline_images = confirmation_email(sales_order, confirmation_url)
		frappe.sendmail(
			recipients=[email],
			subject=_("Your order {0} is confirmed").format(sales_order.name),
			message=message,
			inline_images=inline_images,
			reference_doctype="Sales Order",
			reference_name=sales_order.name,
		)
	except Exception:
		frappe.log_error(title="Order confirmation email failed")


# An inbox keeps no stylesheet and runs no script, so the receipt is built
# from tables and inline declarations alone — no flex, no grid, nothing that
# has to be laid out by anything but the mail client itself.
_EMAIL_FONT = "-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Helvetica,Arial,sans-serif"
_EMAIL_MONO = "SFMono-Regular,Menlo,Consolas,Liberation Mono,monospace"
_EMAIL_INK = "#18181b"
_EMAIL_MUTED = "#71717a"
_EMAIL_LINE = "#e4e4e7"
_EMAIL_SOFT = "#f4f4f5"


def _email_style(**props) -> str:
	"""An inline style built from keyword properties; underscores are dashes.

	Declarations one by one rather than the shorthand ``font`` property:
	Gmail meets a shorthand it cannot parse by discarding the whole
	declaration, which would drop the typeface off half the receipt."""
	return ";".join(f"{key.replace('_', '-')}:{value}" for key, value in props.items())


def confirmation_email(sales_order, confirmation_url: str) -> tuple[str, list[dict]]:
	"""The confirmation email: its HTML and the images that travel inside it.

	The confirmation page prints a Receipt tile promising this mail, so the
	mail repeats the page — progress, items, totals, the way the order is
	being paid for, and where it is going — because a customer who keeps it
	should be able to read their whole order without opening a link.

	Email runs no JavaScript, which decides two of the page's controls. The
	Copy IBAN and Copy details buttons are answered by what they would have
	copied: the transfer block set as text a thumb can select. Download QR
	is answered by the code itself, inlined as an image the inbox keeps on
	the message, so it can be saved or scanned straight from there. Every
	other control becomes a link, which is the whole of what mail can
	honestly offer; the page keeps the buttons it can actually press.
	"""
	import base64

	from shop.storefront import orders as orders_module

	settings = frappe.get_cached_doc("Shop Settings")
	summary = orders_module.order_summary(sales_order)
	escape = frappe.utils.escape_html
	raw_name = summary["name"]
	store = escape((settings.store_name or _("our store")).strip())
	name = escape(raw_name)
	method = summary["payment_method"]
	images: list[dict] = []

	def section(text, color=_EMAIL_MUTED):
		"""The mono, letter-spaced heading the confirmation page prints."""
		css = _email_style(
			margin="0 0 8px",
			font_family=_EMAIL_MONO,
			font_size="10px",
			font_weight="600",
			letter_spacing="0.14em",
			text_transform="uppercase",
			color=color,
		)
		return f"<p style='{css}'>{escape(text)}</p>"

	def band(content, top="18px", bottom="0", extra=None):
		"""One full-width band of the card, guttered like the panel."""
		css = _email_style(padding=f"{top} 28px {bottom}", **(extra or {}))
		return f"<tr><td style='{css}'>{content}</td></tr>"

	def chip(text, done):
		css = _email_style(
			display="inline-block",
			margin="0 6px 6px 0",
			padding="6px 11px",
			border_radius="999px",
			font_family=_EMAIL_MONO,
			font_size="10px",
			font_weight="600",
			letter_spacing="0.1em",
			line_height="1.3",
			text_transform="uppercase",
			background_color=_EMAIL_INK if done else _EMAIL_SOFT,
			color="#ffffff" if done else _EMAIL_MUTED,
		)
		return f"<span style='{css}'>{('&check; ' if done else '')}{escape(text)}</span>"

	def money_row(text, value, strong=False):
		left = _email_style(
			padding="7px 0",
			font_size="15px" if strong else "13px",
			font_weight="700" if strong else "400",
			color=_EMAIL_INK,
			border_top=f"1px solid {_EMAIL_LINE}" if strong else "none",
		)
		right = _email_style(
			padding="12px 0 7px" if strong else "7px 0",
			text_align="right",
			font_size="15px" if strong else "13px",
			font_weight="700" if strong else "400",
			color=_EMAIL_INK,
			border_top=f"1px solid {_EMAIL_LINE}" if strong else "none",
		)
		return (
			"<tr>"
			f"<td style='{left}'>{escape(text)}</td>"
			f"<td align='right' style='{right}'>{escape(value)}</td>"
			"</tr>"
		)

	def button(text, href, solid=True, small=False):
		"""A link wearing the page's pill: mail cannot press a real button."""
		css = _email_style(
			display="inline-block",
			margin="0 8px 8px 0",
			padding="10px 16px" if small else "13px 24px",
			border_radius="999px",
			border=f"1px solid {_EMAIL_INK}",
			font_family=_EMAIL_MONO,
			font_size="10px" if small else "11px",
			font_weight="600",
			letter_spacing="0.12em",
			line_height="1.2",
			text_align="center",
			text_decoration="none",
			text_transform="uppercase",
			background_color=_EMAIL_INK if solid else "transparent",
			color="#ffffff" if solid else _EMAIL_INK,
		)
		return f"<a href='{escape(href)}' style='{css}'>{escape(text)}</a>"

	def link(text, href, color="#ffffff"):
		css = _email_style(color=color, font_family=_EMAIL_MONO, font_size="11px",
			letter_spacing="0.12em", text_transform="uppercase", text_decoration="underline")
		return f"<a href='{escape(href)}' style='{css}'>{escape(text)}</a>"

	# --- what the order is ---------------------------------------------
	item_cell = _email_style(
		padding="11px 0", border_bottom=f"1px solid {_EMAIL_LINE}", font_size="14px", color=_EMAIL_INK
	)
	qty_css = _email_style(color=_EMAIL_MUTED, font_size="12px")
	item_rows = "".join(
		"<tr>"
		f"<td style='{item_cell}'>{escape(str(row['item_name']))} "
		f"<span style='{qty_css}'>&times; {escape(str(row['qty']))}</span></td>"
		f"<td align='right' style='{item_cell}'>{escape(row['formatted_amount'])}</td>"
		"</tr>"
		for row in summary["items"]
	)
	totals = [money_row(_("Subtotal"), summary["formatted_total"])]
	if summary["formatted_discount"]:
		totals.append(money_row(_("Discount"), f"-{summary['formatted_discount']}"))
	totals.append(money_row(_("Shipping"), summary["formatted_shipping"] or _("Free")))
	totals.append(money_row(_("Total"), summary["formatted_grand_total"], strong=True))
	summary_block = band(
		section(_("Order summary"))
		+ f"<table role='presentation' width='100%' cellpadding='0' cellspacing='0' border='0' style='width:100%;border-collapse:collapse;'>"
		+ item_rows
		+ "".join(totals)
		+ "</table>"
	)

	# --- how it is being paid ------------------------------------------
	raast = summary["raast"] or {}
	advance = summary["advance_payment"] or {}
	status_chip = summary["payment_status"] or ""
	payment_block = ""

	def pay_head(title, dark):
		"""Title and the ledger's own status, facing each other."""
		title_css = _email_style(
			margin="0", font_family=_EMAIL_MONO, font_size="10px", font_weight="600",
			letter_spacing="0.16em", text_transform="uppercase",
			color="#ffffff" if dark else _EMAIL_INK,
		)
		chip_css = _email_style(
			display="inline-block", padding="5px 12px", border_radius="999px",
			border=f"1px solid {'rgba(255,255,255,0.45)' if dark else _EMAIL_LINE}",
			font_family=_EMAIL_MONO, font_size="9px", font_weight="600",
			letter_spacing="0.14em", text_transform="uppercase",
			color="#ffffff" if dark else _EMAIL_INK,
		)
		inner = _email_style(padding="0", font_size="0")
		return (
			"<table role='presentation' width='100%' cellpadding='0' cellspacing='0' border='0' "
			f"style='width:100%;'><tr><td style='{inner}'><p style='{title_css}'>{escape(title)}</p></td>"
			f"<td align='right' style='{inner}'><span style='{chip_css}'>{escape(status_chip)}</span></td></tr></table>"
		)

	def detail(label_text, value, dark=True, mono=False):
		"""One label over one value — the panel's Account title / Bank / IBAN."""
		if not value:
			return ""
		label_css = _email_style(
			margin="14px 0 0", font_family=_EMAIL_MONO, font_size="9px", font_weight="600",
			letter_spacing="0.16em", text_transform="uppercase",
			color="rgba(255,255,255,0.6)" if dark else _EMAIL_MUTED,
		)
		value_css = _email_style(
			margin="4px 0 0", font_size="15px", font_weight="600",
			color="#ffffff" if dark else _EMAIL_INK,
			font_family=_EMAIL_MONO if mono else _EMAIL_FONT,
			letter_spacing="0.04em" if mono else "normal",
		)
		return f"<p style='{label_css}'>{escape(label_text)}</p><p style='{value_css}'>{escape(str(value))}</p>"

	if method == "raast" and raast:
		# The QR panel, inverted exactly as the page inverts it: what is owed
		# leads, the account sits under it, and the code is framed in white
		# so it scans off a dark message as easily as off the page.
		left = [pay_head(_("Advance payment"), dark=True)]
		amount_css = _email_style(
			margin="16px 0 0", font_size="32px", font_weight="600", line_height="1.1",
			letter_spacing="-0.02em", color="#ffffff",
		)
		left.append(f"<p style='{amount_css}'>{escape(raast['formatted_amount'])}</p>")
		line_css = _email_style(margin="8px 0 0", font_size="13px", line_height="1.6",
			color="rgba(255,255,255,0.78)")
		left.append(f"<p style='{line_css}'>{escape(raast.get('line') or '')}</p>")
		left.append(
			f"<div style='{_email_style(height='1px', margin='16px 0 0', background_color='rgba(255,255,255,0.16)', font_size='0')}'>"
			"&nbsp;</div>"
		)
		left.append(detail(_("Account title"), raast.get("account_title")))
		left.append(detail(_("Bank"), raast.get("bank")))
		left.append(detail(_("Raast IBAN"), raast.get("iban"), mono=True))
		# No transfer block here: the panel repeats what the three rows above
		# it already say — title, bank, IBAN, with the amount heading the box
		# and the order number in the headline. The page's paste-ready note
		# stays where it can be pasted from, behind its Copy buttons.
		right = []
		qr_image = ""
		if raast.get("qr_data_url"):
			try:
				png = base64.b64decode(raast["qr_data_url"].partition(",")[2])
			except Exception:
				png = b""
			if png:
				images.append({"filename": "raast-qr.png", "filecontent": png})
				img_css = _email_style(
					display="block", width="240px", max_width="100%", height="auto",
					margin="0 auto", border_radius="6px",
				)
				qr_image = f"<img embed='raast-qr.png' alt='{escape(_('Raast QR code'))}' width='240' style='{img_css}'>"
		if qr_image:
			frame_css = _email_style(
				background_color="#ffffff", border_radius="12px", padding="12px", text_align="center"
			)
			caption_css = _email_style(
				margin="10px 0 0", font_size="11px", letter_spacing="0.06em",
				text_align="center", color="rgba(255,255,255,0.62)",
			)
			valid_css = _email_style(margin="6px 0 0", font_size="11px", text_align="center",
				color="rgba(255,255,255,0.62)")
			right.append(f"<div style='{frame_css}'>{qr_image}</div>")
			right.append(f"<p style='{caption_css}'>{escape(_('Raast QR code — scan with banking app'))}</p>")
			if raast.get("valid_until"):
				right.append(
					f"<p style='{valid_css}'>{escape(_('Valid until {0}').format(raast['valid_until']))}</p>"
				)
		foot = []
		# No instructions note here either: that text is checkout's, for the
		# moment before the order exists. Above this line sits the code it
		# would be talking about.
		foot.append(
			f"<p style='{_email_style(margin='12px 0 0', font_size='12px', line_height='1.6', color='rgba(255,255,255,0.72)')}'>"
			f"{escape(_('Open your order to copy the account details in one tap or save the QR to your phone.'))}</p>"
		)
		foot.append(link(_("View your order"), frappe.utils.get_url(confirmation_url)))
		left_cell = _email_style(padding="22px 18px 20px 22px", vertical_align="top", width="58%")
		right_cell = _email_style(padding="22px 22px 20px 6px", vertical_align="top", width="42%")
		payment_block = band(
			"<table role='presentation' width='100%' cellpadding='0' cellspacing='0' border='0' "
			"style='width:100%;background-color:#18181b;border-radius:16px;'><tr>"
			f"<td style='{left_cell}'>{''.join(left)}</td>"
			f"<td style='{right_cell}'>{''.join(right)}</td></tr>"
			f"<tr><td colspan='2' style='{_email_style(padding='0 22px 22px')}'>{''.join(foot)}</td></tr>"
			"</table>",
			top="20px",
		)
	elif method in ("advance", "cod", "pickup", "gateway"):
		# No QR to frame: the same facts in the panel's light clothing —
		# what is owed, in the store's own words, with the ledger's status.
		title = _("Advance payment") if method == "advance" else _("Payment")
		if method == "advance":
			figure = advance.get("formatted_advance_amount") or summary["formatted_grand_total"]
			line = advance.get("line") or ""
		elif method == "pickup":
			figure = summary["formatted_grand_total"]
			line = _("Pay {0} when you collect your order.").format(summary["formatted_grand_total"])
		elif method == "cod":
			figure = summary["formatted_grand_total"]
			line = _("Pay {0} in cash when your order arrives.").format(summary["formatted_grand_total"])
		else:
			figure = summary["formatted_grand_total"]
			line = _("Payment is completed through our secure online checkout.")
		figure_css = _email_style(margin="14px 0 0", font_size="26px", font_weight="600",
			letter_spacing="-0.02em", color=_EMAIL_INK)
		line_css = _email_style(margin="6px 0 0", font_size="13px", line_height="1.6", color=_EMAIL_MUTED)
		parts = [pay_head(title, dark=False), f"<p style='{figure_css}'>{escape(figure)}</p>",
			f"<p style='{line_css}'>{escape(line)}</p>"]
		frame = _email_style(
			background_color=_EMAIL_SOFT, border=f"1px solid {_EMAIL_LINE}",
			border_radius="16px", padding="18px 20px",
		)
		payment_block = band(f"<table role='presentation' width='100%' cellpadding='0' cellspacing='0' "
			f"border='0' style='width:100%;'><tr><td style='{frame}'>{''.join(parts)}</td></tr></table>", top="20px")

	# --- where it is going ---------------------------------------------
	destination = ""
	if method == "pickup" and summary.get("pickup_location"):
		location = summary["pickup_location"]
		body = [section(_("Pickup"))]
		place_css = _email_style(margin="0", font_size="14px", font_weight="700", color=_EMAIL_INK)
		body.append(f"<p style='{place_css}'>{escape(location.get('name') or _('Store pickup'))}</p>")
		text_css = _email_style(margin="4px 0 0", font_size="13px", line_height="1.65", color=_EMAIL_MUTED)
		if location.get("address"):
			body.append(f"<p style='{text_css}'>{escape(location['address'])}</p>")
		# The number reads as a line of the address — under it, not beside
		# the buttons — and the buttons take the row beneath, the order the
		# page lists them in: where, how to reach it, how to get there.
		if location.get("phone"):
			phone_row = _email_style(margin="8px 0 0", font_size="13px", line_height="1.5")
			phone_css = _email_style(color=_EMAIL_INK, text_decoration="underline")
			dial = location.get("phone_dial") or f"tel:{location['phone']}"
			body.append(
				f"<p style='{phone_row}'><a href='{escape(dial)}' style='{phone_css}'>"
				f"{escape(location['phone'])}</a></p>"
			)
		controls = []
		if location.get("directions_url"):
			controls.append(button(_("Get directions"), location["directions_url"], solid=True, small=True))
		if location.get("whatsapp_url"):
			controls.append(button(_("WhatsApp"), location["whatsapp_url"], solid=False, small=True))
		if controls:
			body.append(
				f"<p style='{_email_style(margin='14px 0 0', font_size='0')}'>{''.join(controls)}</p>"
			)
		frame = _email_style(background_color=_EMAIL_SOFT, border=f"1px solid {_EMAIL_LINE}",
			border_radius="12px", padding="16px 18px")
		destination = band(
			f"<table role='presentation' width='100%' cellpadding='0' cellspacing='0' border='0' "
			f"style='width:100%;'><tr><td style='{frame}'>{''.join(body)}</td></tr></table>"
		)
	else:
		address = None
		if sales_order.customer_address:
			try:
				address = frappe.get_doc("Address", sales_order.customer_address)
			except Exception:
				address = None
		recipient = (getattr(address, "address_title", None) or sales_order.customer_name or "").strip()
		street = ", ".join(
			p for p in ((getattr(address, "address_line1", None) or ""), (getattr(address, "address_line2", None) or "")) if p
		)
		city_line = ", ".join(
			p for p in ((getattr(address, "city", None) or ""), (getattr(address, "pincode", None) or "")) if p
		)
		region = ", ".join(
			p for p in ((getattr(address, "state", None) or ""), (getattr(address, "country", None) or "")) if p
		)
		landmark = (getattr(address, "custom_landmark", None) or "").strip()
		phone = (sales_order.contact_phone or getattr(address, "phone", None) or "").strip()
		if recipient or street or city_line:
			body = [section(_("Deliver to"))]
			if recipient:
				place_css = _email_style(margin="0", font_size="14px", font_weight="700", color=_EMAIL_INK)
				body.append(f"<p style='{place_css}'>{escape(recipient)}</p>")
			text_css = _email_style(margin="4px 0 0", font_size="13px", line_height="1.65", color=_EMAIL_MUTED)
			for line in (street, city_line, region):
				if line:
					body.append(f"<p style='{text_css}'>{escape(line)}</p>")
			if landmark:
				body.append(
					f"<p style='{text_css}'>{escape(_('Landmark: {0}').format(landmark))}</p>"
				)
			if phone:
				body.append(f"<p style='{text_css}'>{escape(_('Phone: {0}').format(phone))}</p>")
			frame = _email_style(background_color=_EMAIL_SOFT, border=f"1px solid {_EMAIL_LINE}",
				border_radius="12px", padding="16px 18px")
			destination = band(
				f"<table role='presentation' width='100%' cellpadding='0' cellspacing='0' border='0' "
				f"style='width:100%;'><tr><td style='{frame}'>{''.join(body)}</td></tr></table>"
			)

	# --- the page's two info tiles --------------------------------------
	tiles = []
	if method != "pickup":
		tiles.append(
			(section(_("Shipping"))
			 + f"<p style='{_email_style(margin='0', font_size='12px', line_height='1.6', color=_EMAIL_MUTED)}'>"
			 + escape(_("Your order ships in 48 hours. We will email you the tracking number.")) + "</p>")
		)
	tiles.append(
		(section(_("Receipt"))
		 + f"<p style='{_email_style(margin='0', font_size='12px', line_height='1.6', color=_EMAIL_MUTED)}'>"
		 + escape(_("Keep this email — it is your receipt for order {0}.").format(raw_name)) + "</p>")
	)
	tile_css = _email_style(
		background_color=_EMAIL_SOFT, border_radius="12px", padding="14px 16px", vertical_align="top"
	)
	# One tile (a pickup order has no shipping line to face) takes the whole
	# row rather than leaving a hole where its neighbour would have been —
	# the same empty-cell problem the page solves by giving Shipping and
	# Receipt a row of their own.
	tile_left = _email_style(padding="0 6px 0 0", vertical_align="top",
		width="100%" if len(tiles) == 1 else "50%")
	tile_right = _email_style(padding="0 0 0 6px", vertical_align="top", width="50%")
	cells = "".join(
		f"<td style='{tile_left if i == 0 else tile_right}'><table role='presentation' width='100%' "
		f"cellpadding='0' cellspacing='0' border='0' style='width:100%;'><tr>"
		f"<td style='{tile_css}'>{tile}</td></tr></table></td>"
		for i, tile in enumerate(tiles)
	)
	tiles_html = f"<tr>{cells}</tr>"
	tiles_block = band(
		"<table role='presentation' width='100%' cellpadding='0' cellspacing='0' border='0' "
		f"style='width:100%;'>{tiles_html}</table>",
		top="20px",
	)

	# --- the controls, as links ----------------------------------------
	controls = "".join(
		[
			button(_("View your order"), frappe.utils.get_url(confirmation_url), solid=True),
			button(_("Track my order"), frappe.utils.get_url("/account/orders"), solid=False),
			button(_("Continue shopping"), frappe.utils.get_url("/products"), solid=False),
		]
	)
	controls_block = band(f"<p style='{_email_style(margin='0', font_size='0')}'>{controls}</p>", top="22px")

	progress_block = band(
		"".join(chip(stage["label"], stage.get("done") == "true") for stage in summary["progress"]),
		top="18px",
		extra={"font_size": "0"},
	)

	# --- masthead and footer -------------------------------------------
	brand_css = _email_style(
		margin="0", font_family=_EMAIL_MONO, font_size="10px", font_weight="600",
		letter_spacing="0.18em", text_transform="uppercase", color=_EMAIL_MUTED,
	)
	headline_css = _email_style(
		margin="14px 0 0", font_size="24px", font_weight="600", line_height="1.25",
		letter_spacing="-0.01em", color=_EMAIL_INK,
	)
	intro_css = _email_style(margin="8px 0 0", font_size="14px", line_height="1.6", color=_EMAIL_MUTED)
	head = band(
		f"<p style='{brand_css}'>{store} &nbsp;·&nbsp; {escape(_('Receipt'))}</p>"
		f"<h1 style='{headline_css}'>{escape(_('Order {0} confirmed').format(raw_name))}</h1>"
		f"<p style='{intro_css}'>{escape(_('Thank you for your order at {0} — everything about it is below.').format((settings.store_name or _('our store')).strip()))}</p>",
		top="26px",
	)
	foot_css = _email_style(
		margin="0", font_family=_EMAIL_MONO, font_size="10px", letter_spacing="0.1em",
		text_transform="uppercase", color=_EMAIL_MUTED,
	)
	tail = band(
		f"<p style='{foot_css}'>{store} &nbsp;·&nbsp; {escape(summary['display_status'])} "
		f"&nbsp;·&nbsp; {escape(str(summary['transaction_date']))}</p>",
		top="20px",
		bottom="26px",
	)

	shell_outer = _email_style(background_color=_EMAIL_SOFT, padding="24px 12px")
	shell_card = _email_style(
		width="100%", max_width="600px", background_color="#ffffff", border=f"1px solid {_EMAIL_LINE}",
		border_radius="16px", border_collapse="separate",
	)
	html = (
		"<table role='presentation' width='100%' cellpadding='0' cellspacing='0' border='0' "
		f"style='{shell_outer}'><tr><td align='center'>"
		"<table role='presentation' width='600' cellpadding='0' cellspacing='0' border='0' "
		f"style='{shell_card}'>"
		+ head
		+ progress_block
		+ summary_block
		+ payment_block
		+ destination
		+ tiles_block
		+ controls_block
		+ tail
		+ "</table></td></tr></table>"
	)
	return html, images


@contextmanager
def elevated():
	# ERPNext's SO validation requires Item read perms no shopper role has.
	# Inputs are fully validated before elevation; scope approved for guest checkout.
	# set_user mutates session.sid/data in place, so restore the whole identity
	# or the response reissues a broken sid cookie and logs the shopper out.
	session = frappe.local.session
	original = (session.user, session.sid, session.data)
	frappe.set_user("Administrator")
	try:
		yield
	finally:
		session.user, session.sid, session.data = original
		frappe.local.cache = {}
		frappe.local.role_permissions = {}


def cod_cities(settings=None) -> list[str]:
	"""Lowercased cities where cash on delivery is offered; empty means all."""
	settings = settings or frappe.get_cached_doc("Shop Settings")
	raw = getattr(settings, "cod_allowed_cities", None) or ""
	return [c.strip().lower() for c in raw.split(",") if c.strip()]


def validate_order(cart, customer: dict, address: dict, payment_method: str, pickup_location: str = ""):
	if not cart or not cart.items:
		frappe.throw(_("Your cart is empty"))
	settings = frappe.get_cached_doc("Shop Settings")
	if payment_method == "cod" and not settings.enable_cod:
		frappe.throw(_("Cash on Delivery is not available"))
	if payment_method == "cod":
		allowed = cod_cities(settings)
		city = (address.get("city") or "").strip()
		if allowed and city.lower() not in allowed:
			# Name the method the checkout is offering. Both rows are called
			# Advance Payment now — one simply has a QR behind it — so either
			# way the customer is pointed at the same name.
			alternative = _("Advance Payment")
			frappe.throw(
				_("Cash on Delivery is not offered in {0}. Please choose {1} or pay online.").format(
					city or _("this city"), alternative
				)
			)
	if payment_method == "gateway" and not settings.payment_gateway_account:
		frappe.throw(_("Online payment is not available"))
	if payment_method == "advance" and not settings.enable_advance_payment:
		frappe.throw(_("Advance payment is not available"))
	if payment_method == "raast" and not raast_module.configured(settings):
		frappe.throw(_("Advance payment is not available"))
	if payment_method == "pickup":
		pickup_module.resolve(pickup_location, settings)
	validate_email_address(customer.get("email"), throw=True)
	if not customer.get("full_name"):
		frappe.throw(_("Name is required"))
	# Landmarks guide delivery riders; pickup orders are collected in person.
	if cint(settings.landmark_required) and payment_method != "pickup":
		landmark = (address.get("landmark") or address.get("custom_landmark") or "").strip()
		if not landmark:
			frappe.throw(_("Nearest landmark is required so delivery riders can find you. (Received: {})").format(str(address)))
	validate_stock(cart)


def validate_stock(cart):
	settings = frappe.get_cached_doc("Shop Settings")
	for row in cart.items:
		cart_module.validate_purchasable(row.item_code)
		if settings.allow_out_of_stock:
			continue
		if not frappe.get_cached_value("Item", row.item_code, "is_stock_item"):
			continue
		available = stock.get_stock([row.item_code]).get(row.item_code, 0)
		if available < flt(row.qty):
			frappe.throw(_("Only {0} of {1} left in stock").format(int(available), row.item_code))


def get_or_create_customer(customer: dict) -> str:
	email = customer["email"].strip().lower()
	phone = (customer.get("phone") or "").strip()
	
	existing = None
	if phone:
		contact_by_phone = frappe.db.get_value("Contact Phone", {"phone": phone}, "parent")
		if contact_by_phone:
			existing = frappe.db.get_value("Dynamic Link", {"parent": contact_by_phone, "link_doctype": "Customer"}, "link_name")
			
	if not existing:
		existing = find_customer_by_email(email)
		
	if existing:
		if phone:
			contact = frappe.db.get_value("Dynamic Link", {"link_doctype": "Customer", "link_name": existing, "parenttype": "Contact"}, "parent")
			if contact and not frappe.db.exists("Contact Phone", {"parent": contact, "phone": phone}):
				contact_doc = frappe.get_doc("Contact", contact)
				contact_doc.add_phone(phone, is_primary_mobile_no=True)
				contact_doc.save(ignore_permissions=True)
		return existing
		
	party = frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": customer["full_name"],
			"customer_type": "Individual",
		}
	).insert(ignore_permissions=True)
	create_contact(party.name, customer, email)
	return party.name


def find_customer_by_email(email: str) -> str | None:
	contact = frappe.db.get_value("Contact Email", {"email_id": email}, "parent")
	if not contact:
		return None
	return frappe.db.get_value(
		"Dynamic Link",
		{"parenttype": "Contact", "parent": contact, "link_doctype": "Customer"},
		"link_name",
	)


def create_contact(party: str, customer: dict, email: str):
	contact = frappe.get_doc(
		{
			"doctype": "Contact",
			"first_name": customer["full_name"],
			"links": [{"link_doctype": "Customer", "link_name": party}],
		}
	)
	contact.add_email(email, is_primary=True)
	if customer.get("phone"):
		contact.add_phone(customer["phone"], is_primary_mobile_no=True)
	contact.insert(ignore_permissions=True)


def create_address(party: str, customer: dict, address: dict):
	from shop.integrations.geocoding import address_hash

	hkey = address_hash(address)
	existing = find_address(party, address)
	if existing:
		# bump modified so saved addresses stay ordered by last use
		old_hash = frappe.db.get_value("Address", existing, "custom_address_hash")
		updates = {"custom_address_hash": hkey}
		if old_hash != hkey:
			# landmark changed -> new hash; reset the stale verification summary
			updates.update({
				"custom_verification_status": "",
				"custom_address_risk_score": 0,
				"custom_ors_confidence": 0,
				"custom_latitude": 0,
				"custom_longitude": 0,
				"custom_gms_result_count": 0,
				"custom_last_verified_on": None,
			})
		if address.get("landmark"):
			updates["custom_landmark"] = address.get("landmark")
		if address.get("alt_phone"):
			updates["custom_alt_phone"] = address.get("alt_phone")
		frappe.db.set_value("Address", existing, updates)
		return frappe.get_doc("Address", existing)
	doc = frappe.get_doc(
		{
			"doctype": "Address",
			"address_title": customer["full_name"],
			"address_type": "Shipping",
			"address_line1": address.get("address_line1"),
			"address_line2": address.get("address_line2"),
			"city": address.get("city"),
			"state": address.get("state"),
			"country": address.get("country") or frappe.db.get_default("country"),
			"pincode": address.get("pincode"),
			"phone": customer.get("phone"),
			"email_id": customer.get("email"),
			"custom_landmark": address.get("landmark"),
			"custom_alt_phone": address.get("alt_phone"),
			"custom_address_hash": hkey,
			"links": [{"link_doctype": "Customer", "link_name": party}],
		}
	)
	doc.insert(ignore_permissions=True)
	return doc


def find_address(party: str, address: dict) -> str | None:
	links = frappe.get_all(
		"Dynamic Link",
		filters={"parenttype": "Address", "link_doctype": "Customer", "link_name": party},
		pluck="parent",
	)
	if not links:
		return None
	return frappe.db.get_value(
		"Address",
		{
			"name": ["in", links],
			"address_line1": address.get("address_line1"),
			"city": address.get("city"),
			"pincode": address.get("pincode"),
		},
	)


def create_sales_order(
	cart,
	party: str,
	shipping_address,
	device_fingerprint: str = "",
	customer_data: dict = None,
	fingerprint_provider: str = "",
	payment_method: str = "cod",
	advance_amount: float = 0.0,
	pickup_location: str = "",
):
	settings = frappe.get_cached_doc("Shop Settings")
	cart_module.refresh_rates(cart)
	coupon, discount = cart_module.applied_discount(
		cart, sum(flt(row.rate) * flt(row.qty) for row in cart.items)
	)
	company_currency = frappe.get_cached_value("Company", settings.company, "default_currency")
	sales_order = frappe.get_doc(
		{
			"doctype": "Sales Order",
			"company": settings.company,
			"customer": party,
			"order_type": "Sales",
			"delivery_date": add_days(nowdate(), 3),
			"selling_price_list": settings.price_list,
			"currency": settings.currency or company_currency,
			"conversion_rate": 1,
			"plc_conversion_rate": 1,
			"customer_address": shipping_address.name,
			"shipping_address_name": shipping_address.name,
			"custom_device_fingerprint": device_fingerprint or None,
			"custom_fingerprint_provider": fingerprint_provider or None,
			"custom_payment_method": payment_method or "cod",
			"custom_advance_amount": flt(advance_amount)
			if payment_method in ("advance", "raast")
			else 0,
			"custom_pickup_location": pickup_location or None,
			"contact_email": (customer_data or {}).get("email"),
			"contact_phone": (customer_data or {}).get("phone"),
			"contact_mobile": (customer_data or {}).get("phone"),
			"items": [
				{
					"item_code": row.item_code,
					"qty": row.qty,
					"rate": row.rate,
					"warehouse": settings.default_warehouse,
				}
				for row in cart.items
			],
		}
	)
	if discount:
		sales_order.apply_discount_on = "Grand Total"
		sales_order.discount_amount = discount
	apply_taxes(sales_order, settings)
	if payment_method != "pickup":
		# Pickup hands the order over in person, so there is no courier to charge for.
		apply_shipping(sales_order, settings, discount)
	sales_order.flags.ignore_permissions = True
	sales_order.insert(ignore_permissions=True)
	sales_order.submit()
	if discount:
		from shop.storefront import coupons

		coupons.redeem(cart.coupon_code)
	from shop.api.orders import auto_billing_enabled, create_sales_invoice_for_order

	if auto_billing_enabled():
		# The invoice goes out submitted but unpaid: COD settles it through
		# Mark paid, prepaid orders through the gateway reallocation. Billing
		# must never lose a placed order, so failures are logged, not raised.
		try:
			create_sales_invoice_for_order(sales_order.name)
		except Exception:
			frappe.log_error(
				title="Storefront auto-invoice failed",
				reference_doctype="Sales Order",
				reference_name=sales_order.name,
			)
	return sales_order


def apply_taxes(sales_order, settings):
	if not settings.tax_template:
		return
	from erpnext.controllers.accounts_controller import get_taxes_and_charges

	sales_order.taxes_and_charges = settings.tax_template
	for tax in get_taxes_and_charges("Sales Taxes and Charges Template", settings.tax_template) or []:
		sales_order.append("taxes", tax)


def apply_shipping(sales_order, settings, discount: float):
	subtotal = sum(flt(row.qty) * flt(row.rate) for row in sales_order.items)
	shipping = cart_module.shipping_charge(subtotal - flt(discount))
	if not shipping:
		return
	sales_order.append(
		"taxes",
		{
			"charge_type": "Actual",
			"account_head": settings.shipping_account,
			"description": _("Shipping"),
			"tax_amount": shipping,
		},
	)


def convert_cart(cart, sales_order):
	cart.status = "Converted"
	cart.sales_order = sales_order.name
	cart.save(ignore_permissions=True)


def create_payment_request(sales_order, customer: dict) -> str | None:
	from erpnext.accounts.doctype.payment_request.payment_request import make_payment_request

	settings = frappe.get_cached_doc("Shop Settings")
	payment_request = make_payment_request(
		dt="Sales Order",
		dn=sales_order.name,
		recipient_id=customer.get("email"),
		payment_gateway_account=settings.payment_gateway_account,
		submit_doc=1,
		mute_email=1,
		return_doc=1,
	)
	return payment_request.get_payment_url()
