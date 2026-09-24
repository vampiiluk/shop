import { expect, test } from "@playwright/test";
import { addToCartViaPDP, fillCheckout } from "./personas/helpers";

const BUYER = {
	email: `buyer-${Date.now()}@example.com`,
	full_name: "Ada Buyer",
	phone: `98${Math.floor(Math.random() * 1e8).toString().padStart(8, "0")}`,
	address_line1: "42 Test Lane",
	city: "Bengaluru",
	state: "Karnataka",
	pincode: "560001",
};

test.describe("storefront", () => {
	test("home renders store and products", async ({ page }) => {
		const response = await page.request.get("/api/method/shop.storefront.page_data.home");
		const storeName = (await response.json()).message.store.name;
		await page.goto("/");
		await expect(page.locator("body")).toContainText(storeName);
		await expect(page.locator('a[href*="/product/"]').first()).toBeVisible();
	});

	test("listing shows products and search works", async ({ page }) => {
		await page.goto("/products");
		await expect(page.locator('a[href*="/product/ceramic-mug"]').first()).toBeVisible();
		await page.goto("/products?search=mug");
		await expect(page.locator('a[href*="/product/ceramic-mug"]').first()).toBeVisible();
		await expect(page.locator('a[href*="/product/zip-hoodie"]')).toHaveCount(0);
	});

	test("filter presets narrow the listing", async ({ page }) => {
		await page.goto("/products?price=0-500");
		await expect(page.locator('a[href*="/product/enamel-pin-set"]').first()).toBeVisible();
		await expect(page.locator('a[href*="/product/ceramic-mug"]')).toHaveCount(0);
		await page.goto("/products?collection=stationery&sort=price_desc");
		await expect(page.locator('a[href*="/product/oak-desk-organizer"]').first()).toBeVisible();
		await expect(page.locator('a[href*="/product/ceramic-mug"]')).toHaveCount(0);
	});

	test("default pages render", async ({ page }) => {
		for (const path of ["/about", "/contact", "/faq"]) {
			await page.goto(path);
			await expect(page.locator("h1").first()).toBeVisible();
		}
	});

	test("the gallery swaps the main image from thumbnails and variants", async ({ page }) => {
		await page.goto("/product/crew-neck-t-shirt");
		const main = page.locator('[data-shop="main-image"]');
		const thumbs = page.locator('[data-shop="thumb"]');
		expect(await thumbs.count()).toBeGreaterThan(1);

		const first = await thumbs.nth(0).getAttribute("data-image");
		const second = await thumbs.nth(1).getAttribute("data-image");
		expect(first).not.toEqual(second);

		await thumbs.nth(0).click();
		await expect(main).toHaveAttribute("src", first!);
		await expect(thumbs.nth(0)).toHaveAttribute("data-selected", "true");

		await thumbs.nth(1).click();
		await expect(main).toHaveAttribute("src", second!);

		await page.locator('[data-shop="variant-option"][data-value="Black"]').click();
		await expect(main).toHaveAttribute("src", first!);
		await page.locator('[data-shop="variant-option"][data-value="White"]').click();
		await expect(main).toHaveAttribute("src", second!);
	});

	test("checkout address cascade: city sets province, province clears stray city", async ({ page }) => {
		await addToCartViaPDP(page, "crew-neck-t-shirt");
		await page.goto("/checkout");

		const map = await page.evaluate(() => {
			const data = (window as any).page_data || {};
			return (data.store || data).province_city_map as Record<string, string[]>;
		});
		expect(Object.keys(map).length).toBeGreaterThan(0);
		const [province, cities] = Object.entries(map)[0];
		expect(cities.length).toBeGreaterThan(0);

		// Inject a province that is not in the table so both directions of the
		// cascade are observable (the store configures a single province).
		await page.evaluate(() => {
			const state = document.querySelector('[name="state"]') as HTMLSelectElement | null;
			if (!state) return;
			const opt = document.createElement("option");
			opt.value = "__other";
			opt.textContent = "Other Province";
			state.appendChild(opt);
		});
		await page.selectOption('[name="state"]', "__other");

		// city → province: picking a city selects the province it belongs to
		await page.selectOption('[name="city"]', cities[0]);
		await expect(page.locator('[name="state"]')).toHaveValue(province);

		// province → city: a city outside the chosen province is cleared
		await page.selectOption('[name="state"]', "__other");
		await expect(page.locator('[name="city"]')).toHaveValue("");
	});

	test("cod option follows the configured COD city list", async ({ page }) => {
		await addToCartViaPDP(page, "crew-neck-t-shirt");
		await page.goto("/checkout");

		const allowed: string[] = await page.evaluate(() => {
			const data = (window as any).page_data || {};
			return (data.store || data).cod_allowed_cities || [];
		});
		test.skip(!allowed.length, "COD city restriction is not configured");

		const codCount = await page.locator('input[name="payment_method"][value="cod"]').count();
		test.skip(!codCount, "COD is disabled");

		const cities = await page.evaluate(() =>
			Array.from(document.querySelectorAll('[name="city"] option'))
				.map((option) => (option as HTMLOptionElement).value)
				.filter((value) => value),
		);
		const allowedCity = cities.find((city) => allowed.includes(city.toLowerCase()));
		expect(allowedCity).toBeTruthy();

		// Each payment option is a <label> wrapping its radio input.
		const codLabel = page
			.locator('input[name="payment_method"][value="cod"]')
			.locator("xpath=ancestor::label[1]");

		const disallowed = cities.find((city) => !allowed.includes(city.toLowerCase()));
		if (disallowed) {
			// A city outside the list hides the COD option entirely.
			await page.selectOption('[name="city"]', disallowed);
			await expect(codLabel).toBeHidden();
		}
		await page.selectOption('[name="city"]', allowedCity!);
		await expect(codLabel).toBeVisible();
	});

	test("checkout auto-selects the store's single country", async ({ page }) => {
		await addToCartViaPDP(page, "crew-neck-t-shirt");
		await page.goto("/checkout");

		// The country list mirrors the one country configured in Shop Settings.
		const countries = await page.evaluate(() => {
			const data = (window as any).page_data || {};
			const raw = (data.store || data).address_country;
			const rows = Array.isArray(raw) ? raw : [{ name: raw }];
			return rows
				.map((row: any) => (typeof row === "string" ? row : row?.name))
				.filter(Boolean);
		});
		test.skip(countries.length !== 1, "auto-select only applies to a single-country store");

		const country = page.locator('[data-shop="checkout-form"] [name="country"]');
		await expect(country).toHaveValue(countries[0], { timeout: 15000 });
	});

	test("full purchase flow: PDP, variant, cart, checkout, confirmation", async ({ page }) => {
		await page.goto("/product/crew-neck-t-shirt");
		await expect(page.locator("body")).toContainText("Crew Neck T-Shirt");

		const medium = page.locator('[data-shop="variant-option"][data-value="Medium"]');
		await medium.click();
		await expect(medium).toHaveAttribute("data-selected", "true");

		const buy = page.locator('[data-shop="add-to-cart"]');
		await expect(buy).toBeEnabled();
		await buy.click();
		await expect(page.locator('[data-shop="cart-count"]').first()).toHaveText("1");

		await page.goto("/cart");
		await expect(page.locator("body")).toContainText("Crew Neck T-Shirt");
		// set_qty reloads the cart page; wait for the document replacement itself
		// (framenavigated also fires for iframes and can resolve too early).
		await page.evaluate(() => ((window as any).__preReload = true));
		await page.locator('[data-shop="qty-inc"]').first().click();
		await page.waitForFunction(() => !(window as any).__preReload);
		await expect(page.locator("body")).toContainText("2");

		await page.goto("/checkout");
		await fillCheckout(page, BUYER);
		await page.locator('[data-shop="checkout-form"] [type="submit"]').click();

		await page.waitForURL(/order-confirmation/);
		await expect(page.locator("body")).toContainText("Crew Neck T-Shirt");
		await expect(page.locator('[data-shop="progress-stage"]')).toHaveCount(4);
		await expect(
			page.locator('[data-shop="progress-stage"][data-done="true"]')
		).toContainText("Order placed");
		const orderId = page.url().match(/order-confirmation\/([^?]+)/)?.[1];
		expect(orderId).toBeTruthy();

		const api = await page.request.get(
			`/api/method/shop.storefront.orders.get_order_summary?name=${orderId}&token=${await token(page)}`
		);
		expect(api.ok()).toBeTruthy();
	});
});

async function token(page): Promise<string> {
	const cookies = await page.context().cookies();
	return cookies.find((c) => c.name === "shop_cart_token")?.value || "";
}
