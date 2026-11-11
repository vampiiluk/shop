/**
 * Saving a file the server sends as a download response.
 *
 * A download is bytes, not JSON, so it cannot go through `call()`. Callers do
 * their own fetch, then hand the response here to be named and saved.
 */

/** The CSRF token the desk's index.html puts on the window. */
export function csrfToken(): string {
	return (window as any).csrf_token || ''
}

/** The filename the server asked for, from the Content-Disposition header. */
export function filenameFrom(disposition: string | null): string {
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
export async function readDownloadError(response: Response, fallback: string): Promise<Error> {
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
	return new Error(`${fallback} (${response.status})`)
}

/** Save a blob the browser received as a download. */
export function saveBlob(blob: Blob, filename: string): void {
	const url = URL.createObjectURL(blob)
	const anchor = document.createElement('a')
	anchor.href = url
	anchor.download = filename
	document.body.appendChild(anchor)
	anchor.click()
	anchor.remove()
	// The object url holds the whole file in memory until it is revoked.
	URL.revokeObjectURL(url)
}
