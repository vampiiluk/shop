"""Where the storefront lives, as an absolute origin.

The desk and the shop are served from different hosts - the desk on
desk.reloop.pk, the shop on reloop.pk - so a relative path in the desk resolves
against the desk, not the shop. Anything linking from the desk to the storefront
has to be absolute, and the origin lives here so there is one copy of it.

frappe.utils.get_url() is not usable: behind this proxy it reports the bench's
own http://…:8000 address, which is not reachable from outside.
"""

SITE_BASE = "https://reloop.pk"


def storefront_url(path: str = "") -> str:
    """Absolute storefront URL for a root-relative path."""
    return f"{SITE_BASE}/{path.lstrip('/')}" if path else SITE_BASE


def product_url(slug: str) -> str:
    """Absolute URL of one product page."""
    return storefront_url(f"/product/{slug}")
