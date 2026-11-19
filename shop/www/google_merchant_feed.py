"""Serve the Google Merchant Center product feed at a stable public URL.

The feed is generated from the live catalogue on every request, so a price or
stock change is visible to the next fetch without a rebuild. ``no_cache`` tells
Frappe not to store the rendered page, which would otherwise keep serving the
prices from the first hit.

The template lives beside this controller because a www route resolves the
template first; see ``shop/www/sitemap.xml`` for the same arrangement.
"""

from shop.integrations import google_merchant

base_template_path = "www/google_merchant_feed.xml"
no_cache = 1


def get_context(context):
	context.update(google_merchant.feed_context())
	return context
