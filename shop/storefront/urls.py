"""Where the storefront lives, as an absolute origin.

The desk and the shop share a host now - both are reloop.pk, the desk at /desk
and the shop at its own routes - so a root-relative path would happen to resolve
correctly today. It is still built absolute on purpose, for two reasons. One
copy of the origin lives here, so moving the shop is a server-side edit rather
than a change scattered through the frontend; and the day the desk goes back to
a hostname of its own, every "view on storefront" link stays right without a
single call site being revisited.

frappe.utils.get_url() is not usable either way: behind this proxy it reports
the bench's own http://…:8000 address, which is not reachable from outside.
"""

SITE_BASE = "https://reloop.pk"


def storefront_url(path: str = "") -> str:
    """Absolute storefront URL for a root-relative path."""
    return f"{SITE_BASE}/{path.lstrip('/')}" if path else SITE_BASE


def product_url(slug: str) -> str:
    """Absolute URL of one product page."""
    return storefront_url(f"/product/{slug}")
