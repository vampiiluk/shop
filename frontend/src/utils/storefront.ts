import { call } from 'frappe-ui'

/**
 * Absolute storefront links for the desk.
 *
 * The desk and the shop share a host now, so a root-relative path would resolve
 * to the right place today. The links are built absolute anyway: the origin is
 * fetched once from the server rather than written into this bundle, so there is
 * one copy of it and moving the shop's domain stays a server-side edit.
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
