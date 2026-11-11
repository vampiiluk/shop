/**
 * Downloading the products a merchant ticked as a CSV.
 *
 * The file is built on the server so the rules about what each column holds
 * live next to the catalogue, and it is served as a download rather than as
 * JSON so nothing has to be reassembled in the browser.
 */

import { csrfToken, filenameFrom, readDownloadError, saveBlob } from './download'

export async function downloadProductsCsv(names: string[]): Promise<void> {
	const response = await fetch('/api/method/shop.api.products.export_csv', {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json',
			'X-Frappe-CSRF-Token': csrfToken(),
		},
		credentials: 'same-origin',
		body: JSON.stringify({ names }),
	})

	if (!response.ok) {
		throw await readDownloadError(response, 'Could not export the products')
	}

	const filename = filenameFrom(response.headers.get('Content-Disposition')) || 'products.csv'
	saveBlob(await response.blob(), filename)
}
