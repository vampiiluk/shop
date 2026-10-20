import { chromium, expect, test } from '@playwright/test'
import { existsSync, mkdirSync, readFileSync, statSync } from 'fs'
import { join } from 'path'

const BASE = process.env.SHOP_BASE_URL || 'https://reloop.pk'
const DESK = `${BASE}/shop`
const DOWNLOADS = '/tmp/opencode/downloads'

/** The names of the files in a zip, read from its central directory. */
function zipEntries(buffer: Buffer): string[] {
	const names: string[] = []
	// Each central directory record starts with PK\x01\x02, and the length
	// of its name is at offset 28 of the record.
	for (let at = 0; at < buffer.length - 46; at++) {
		if (buffer.readUInt32LE(at) !== 0x02014b50) continue
		const nameLength = buffer.readUInt16LE(at + 28)
		const extraLength = buffer.readUInt16LE(at + 30)
		const commentLength = buffer.readUInt16LE(at + 32)
		names.push(buffer.toString('utf8', at + 46, at + 46 + nameLength))
		at += 45 + nameLength + extraLength + commentLength
	}
	return names
}

test('the social cards button downloads a zip for a product', async ({ page }) => {
	mkdirSync(DOWNLOADS, { recursive: true })

	// The desk's own login, the same way the e2e suite does it.
	const login = await page.request.post(`${BASE}/api/method/login`, {
		data: {
			usr: process.env.SHOP_ADMIN_USER || 'Administrator',
			pwd: process.env.SHOP_ADMIN_PWD || 'admin',
		},
	})
	expect(login.ok(), 'desk login').toBeTruthy()

	const product = await page.request.get(
		`${BASE}/api/method/shop.api.products.get_products?limit=1&status=published`,
	)
	expect(product.ok(), 'products list').toBeTruthy()
	const rows = (await product.json()).message.products
	const name = rows[0].name
	console.log(`  product under test: ${name} (${rows[0].product_name})`)

	// --- the products list: a button on every row --------------------------
	await page.goto(`${DESK}/products`, { waitUntil: 'networkidle' })
	await expect(page.getByRole('heading', { name: 'Products' })).toBeVisible()
	const rowButtons = page.locator('tbody tr button[data-social-cards]')
	const rowCount = await rowButtons.count()
	console.log(`  products list: ${rowCount} social-cards button(s) on the page`)
	expect(rowCount).toBeGreaterThan(0)
	await page.screenshot({ path: join(DOWNLOADS, '01-products-list.png'), fullPage: true })

	// --- the product editor: the button in the image section ---------------
	await page.goto(`${DESK}/products/${encodeURIComponent(name)}`, { waitUntil: 'networkidle' })
	const media = page.locator('section', { has: page.getByRole('heading', { name: 'Media' }) }).first()
	await expect(media).toBeVisible()
	const editorButton = media.locator('button[data-social-cards]')
	await expect(editorButton, 'social cards button in the Media section').toBeVisible()
	const hint = await media.locator('p').last().innerText()
	console.log(`  media hint: ${hint.replace(/\s+/g, ' ').trim()}`)
	await media.scrollIntoViewIfNeeded()
	await page.waitForTimeout(500)
	await media.screenshot({ path: join(DOWNLOADS, '02-product-editor.png') })

	// --- click it and catch the download ------------------------------------
	const waitForDownload = page.waitForEvent('download', { timeout: 120000 })
	await editorButton.click()
	const download = await waitForDownload
	const suggested = download.suggestedFilename()
	const path = join(DOWNLOADS, suggested)
	await download.saveAs(path)
	console.log(`  downloaded: ${suggested}`)

	// The archive is named after the product, not after a slug or a url.
	expect(suggested).toBe(`${rows[0].product_name}.zip`)
	expect(existsSync(path)).toBeTruthy()
	expect(statSync(path).size).toBeGreaterThan(10000)

	// The archive has to be a real zip, with the right cards in it.
	const bytes = readFileSync(path)
	expect(bytes.subarray(0, 2).toString()).toBe('PK')
	const listing = bytes.toString('latin1')
	expect(listing).toContain('social-cards/instagram/')
	expect(listing).toContain('social-cards/tiktok/')

	// Instagram takes one card - the product, its name and its price - and
	// TikTok takes one per photograph, each carrying the words.
	const detail = await page.request.get(
		`${BASE}/api/method/shop.api.products.get_product?name=${encodeURIComponent(name)}`,
	)
	expect(detail.ok(), 'product detail').toBeTruthy()
	const images = (await detail.json()).message.images.length

	// The names are read out of the archive's central directory. Counting
	// them in the raw bytes would count each one twice, because a name is
	// written both in its own header and in the directory.
	const entries = zipEntries(bytes)
	const inFolder = (folder: string) =>
		entries.filter((entry) => entry.startsWith(`social-cards/${folder}/`))
	console.log(
		`  zip holds ${inFolder('instagram').length} instagram card and ${inFolder('tiktok').length} tiktok cards for ${images} photos`,
	)
	expect(inFolder('instagram').length).toBe(1)
	expect(inFolder('tiktok').length).toBe(images)
	expect(entries).toContain('social-cards/README.txt')

	// --- and the products list button does the same -------------------------
	await page.goto(`${DESK}/products`, { waitUntil: 'networkidle' })
	// The list is ordered by ranking, so its first row is not necessarily
	// the product the api returned first: read the name off the row.
	const firstRow = page.locator('tbody tr').first()
	const rowName = (await firstRow.locator('td').nth(1).innerText()).split('\n')[0].trim()
	const listDownload = page.waitForEvent('download', { timeout: 120000 })
	await rowButtons.first().click()
	const file = await listDownload
	console.log(`  list button downloaded: ${file.suggestedFilename()}`)
	expect(file.suggestedFilename()).toBe(`${rowName}.zip`)
})
