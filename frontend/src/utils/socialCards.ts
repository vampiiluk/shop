/**
 * Downloading a product's social cards.
 *
 * The server hands back the archive as a file, not a path, so the browser
 * saves it without a second request and nothing is left on disk. That means
 * the response has to be read as a blob rather than as JSON, which is why
 * this does its own fetch instead of going through `call()`.
 */

import { csrfToken, filenameFrom, readDownloadError, saveBlob } from './download'

/**
 * Ask the server for a product's social cards and save the archive.
 *
 * The card is drawn on the server, so this takes as long as the drawing
 * takes - a few seconds for a product with several photographs.
 */
export async function downloadSocialCards(name: string): Promise<void> {
	const response = await fetch('/api/method/shop.api.social_cards.download', {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json',
			'X-Frappe-CSRF-Token': csrfToken(),
		},
		credentials: 'same-origin',
		body: JSON.stringify({ name }),
	})

	if (!response.ok) {
		throw await readDownloadError(response, 'Could not build the cards')
	}

	const filename = filenameFrom(response.headers.get('Content-Disposition')) || 'social-cards.zip'
	saveBlob(await response.blob(), filename)
}

/** What a download will contain, for the button's description. */
export interface SocialCardSummary {
	images: number
	cards: number
	channels: Record<string, { label: string; width: number; height: number }>
}
