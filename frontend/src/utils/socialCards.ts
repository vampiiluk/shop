/**
 * Downloading a product's social cards.
 *
 * The server hands back the archive as a file, not a path, so the browser
 * saves it without a second request and nothing is left on disk. That means
 * the response has to be read as a blob rather than as JSON, which is why
 * this does its own fetch instead of going through `call()`.
 */

/** The CSRF token the desk's index.html puts on the window. */
function csrfToken(): string {
	return (window as any).csrf_token || ''
}

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
		throw await readError(response)
	}

	const blob = await response.blob()
	const filename = filenameFrom(response.headers.get('Content-Disposition')) || 'social-cards.zip'

	const url = URL.createObjectURL(blob)
	const anchor = document.createElement('a')
	anchor.href = url
	anchor.download = filename
	document.body.appendChild(anchor)
	anchor.click()
	anchor.remove()
	// The object url holds the whole archive in memory until it is revoked.
	URL.revokeObjectURL(url)
}

/** The filename the server asked for, from the Content-Disposition header. */
function filenameFrom(disposition: string | null): string {
	if (!disposition) return ''
	// RFC 5987 puts the real name in filename*=UTF-8''..., which is the form
	// a product name with a space or a non-ASCII character ends up in.
	const extended = disposition.match(/filename\*\s*=\s*[^']*'[^']*'([^;]+)/i)
	if (extended) {
		try {
			return decodeURIComponent(extended[1].trim().replace(/^"|"$/g, ''))
		} catch {
			// Fall through to the plain form.
		}
	}
	const plain = disposition.match(/filename\s*=\s*"([^"]+)"/i) || disposition.match(/filename\s*=\s*([^;]+)/i)
	return plain ? plain[1].trim() : ''
}

/** Turn a failed response into a message worth reading. */
async function readError(response: Response): Promise<Error> {
	try {
		const body = await response.json()
		const messages = body?._server_messages
		if (messages) {
			const parsed = JSON.parse(messages)
			const first = Array.isArray(parsed) ? parsed[0] : parsed
			if (first?.message) return new Error(first.message)
		}
		if (body?.exception) return new Error(body.exception)
	} catch {
		// Not JSON - fall through to the status text.
	}
	return new Error(`Could not build the cards (${response.status})`)
}

/** What a download will contain, for the button's description. */
export interface SocialCardSummary {
	images: number
	cards: number
	channels: Record<string, { label: string; width: number; height: number }>
}
