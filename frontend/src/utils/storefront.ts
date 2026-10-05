import { call } from 'frappe-ui'

/**
 * Absolute storefront links for the desk.
 *
 * The desk runs on desk.reloop.pk and the shop on reloop.pk, so a root-relative
 * path resolves against the desk: "View on storefront" opened the desk, and
 * "View store" did the same. Anything pointing out of the desk has to be
 * absolute.
 *
 * The origin is fetched once from the server rather than written into the
 * bundle, so there is one copy of it and moving the shop's domain is a
 * server-side edit. The index.html that boots this app is served as a static
 * file, so there is no template context to inject into - hence a request.
 */

let pending: Promise<string> | null = null

/** The storefront origin, fetched once and reused. */
export function storefrontBase(): Promise<string> {
	if (!pending) {
		pending = call('shop.api.settings.get_storefront_url')
			.then((payload: { storefront_base_url?: string }) =>
				(payload?.storefront_base_url || '').replace(/\/+$/, ''),
			)
			.catch((error) => {
				// Let the next caller try again rather than caching the failure.
				pending = null
				throw error
			})
	}
	return pending
}

/** Absolute storefront URL for a root-relative path. */
export async function storefrontUrl(path = ''): Promise<string> {
	const base = await storefrontBase()
	return path ? `${base}/${path.replace(/^\/+/, '')}` : base
}

/** Absolute URL of one product page. */
export function productUrl(slug: string): Promise<string> {
	return storefrontUrl(`/product/${slug}`)
}
