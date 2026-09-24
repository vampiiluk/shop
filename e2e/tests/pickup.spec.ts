import { devices, expect, test } from "@playwright/test";
import { addToCartViaPDP, fillCheckout } from "./personas/helpers";

const BUYER = {
	email: `pickup-${Date.now()}@example.com`,
	full_name: "Pia Pickup",
	phone: `97${Math.floor(Math.random() * 1e8).toString().padStart(8, "0")}`,
	address_line1: "7 Collection Counter",
	city: "Bengaluru",
	state: "Karnataka",
	pincode: "560001",
};

interface PickupLocation {
	name: string;
	address: string;
	map_url: string;
	directions_url: string;
}

/** The store may embed OpenStreetMap or (keyless) Google Maps — match whichever. */
function mapSrcSelector(locations: PickupLocation[]): string {
	return locations[0]?.map_url.includes("google.com")
		? 'iframe[src*="maps.google.com"]'
		: 'iframe[src*="openstreetmap.org"]';
}

async function configuredLocations(page: {
	request: import("@playwright/test").APIRequestContext;
}): Promise<PickupLocation[]> {
	const summary = await page.request.get(
		"/api/method/shop.storefront.checkout.get_checkout_summary",
	);
	const message = (await summary.json()).message;
	return (message.pickup_locations || []) as PickupLocation[];
}

test.describe("store pickup", () => {
	test("pickup reveals locations with maps, waives shipping and records the choice", async ({
		page,
	}) => {
		await addToCartViaPDP(page, "ceramic-mug");

		// Gate on the store's own settings: the summary exposes pickup_locations
		// only when pickup is switched on with at least one location.
		const locations = await configuredLocations(page);
		test.skip(!locations.length, "pickup is not configured in Shop Settings");

		await page.goto("/checkout");
		const pickup = page.locator('input[name="payment_method"][value="pickup"]');
		await expect(pickup).toBeVisible();
		await pickup.check();

		// One card per location, each embedding a map of where to collect.
		const panel = page.locator('[data-shop="pickup-panel"]');
		await expect(panel).toBeVisible();
		await expect(panel.locator('input[name="pickup_location"]')).toHaveCount(
			locations.length,
		);
		await expect(panel.locator(mapSrcSelector(locations))).toHaveCount(locations.length);
		await expect(panel).toContainText(locations[0].name);
		await expect(panel).toContainText("no shipping fee");

		// Totals flip to the no-shipping view while pickup is selected.
		await expect(page.locator('[data-shop="delivery-totals"]')).toBeHidden();
		const pickupTotals = page.locator('[data-shop="pickup-totals"]');
		await expect(pickupTotals).toBeVisible();
		await expect(pickupTotals).toContainText("Free");

		// Submitting without a location stays on checkout with an explanation.
		await fillCheckout(page, BUYER);
		await page.locator('[data-shop="checkout-form"] [type="submit"]').click();
		await expect(page.locator("body")).toContainText(
			/choose where you would like to pick up/i,
		);
		await expect(page).toHaveURL(/\/checkout/);

		// Choose a location: the order lands on confirmation with the map tile.
		await panel.locator('input[name="pickup_location"]').first().check();
		await page.locator('[data-shop="checkout-form"] [type="submit"]').click();
		await page.waitForURL(/order-confirmation/, { timeout: 60000 });

		await expect(page.locator("body")).toContainText(locations[0].name);
		await expect(page.locator(mapSrcSelector(locations))).toHaveCount(1);
		// Pickup progress: placed now; ready/picked up release when they pay at the store.
		await expect(page.locator('[data-shop="progress-stage"]')).toHaveCount(4);

		const orderId = page.url().match(/order-confirmation\/([^?]+)/)?.[1];
		expect(orderId).toBeTruthy();

		const cookies = await page.context().cookies();
		const token = cookies.find((c) => c.name === "shop_cart_token")?.value || "";
		const api = await page.request.get(
			`/api/method/shop.storefront.orders.get_order_summary?name=${orderId}&token=${token}`,
		);
		expect(api.ok()).toBeTruthy();
		const order = (await api.json()).message;
		expect(order.payment_method).toBe("pickup");
		expect(order.pickup_location?.name).toBe(locations[0].name);
		expect(order.pickup_location?.map_url).toContain(
			locations[0].map_url.includes("google.com") ? "google.com" : "openstreetmap.org",
		);
		const labels = (order.progress as { label: string }[]).map((stage) => stage.label);
		expect(labels).toContain("Pay at pickup");
	});

	test("direction buttons open Google Maps and the map itself stays view-only", async ({
		page,
	}) => {
		const locations = await configuredLocations(page);
		test.skip(!locations.length, "pickup is not configured in Shop Settings");

		await addToCartViaPDP(page, "ceramic-mug");
		await page.goto("/checkout");
		await page.locator('input[name="payment_method"][value="pickup"]').check();

		const panel = page.locator('[data-shop="pickup-panel"]');
		// One "Get directions" button per card — the transparent overlay that
		// used to sit on the map is gone, so a tap there can't fire the maps app.
		const dirLinks = panel.locator('a[href*="google.com/maps/dir/"]');
		await expect(dirLinks).toHaveCount(locations.length);
		await expect(dirLinks.first()).toContainText("Get directions");
		await expect(
			panel.locator('a[aria-label="Open this location in your maps app"]'),
		).toHaveCount(0);

		// The button opens directions in a new tab.
		const [popup] = await Promise.all([
			page.waitForEvent("popup"),
			dirLinks.first().click(),
		]);
		await popup.waitForLoadState();
		expect(popup.url()).toContain("google.com/maps/dir");
		await popup.close();

		// Clicking the embed itself opens nothing — it is a plain map now.
		let popups = 0;
		page.on("popup", () => popups++);
		await panel
			.locator('iframe[title="Pickup location map"]')
			.first()
			.click({ position: { x: 50, y: 50 }, force: true });
		await page.waitForTimeout(1500);
		expect(popups).toBe(0);
	});
});

test.describe("pickup maps on iPhone", () => {
	// Strip defaultBrowserType (it would force a new worker) and keep only the
	// iPhone emulation — the Apple Maps swap keys off the user agent.
	const { defaultBrowserType: _ignored, ...iphone } = devices["iPhone 13"];
	test.use(iphone);

	test("direction links open Apple Maps instead of Google Maps", async ({ page }) => {
		const locations = await configuredLocations(page);
		test.skip(!locations.length, "pickup is not configured in Shop Settings");

		await addToCartViaPDP(page, "ceramic-mug");
		await page.goto("/checkout");
		await page.locator('input[name="payment_method"][value="pickup"]').check();

		const panel = page.locator('[data-shop="pickup-panel"]');
		// storefront.js rewrites the Google directions button to Apple Maps on
		// iOS; there is no map overlay, so only the button itself is swapped.
		const appleLinks = panel.locator('a[href*="maps.apple.com/?daddr="]');
		await expect(appleLinks).toHaveCount(locations.length);
		await expect(panel.locator('a[href*="google.com/maps/dir/"]')).toHaveCount(0);
		await expect(
			panel.locator('a[aria-label="Open this location in your maps app"]'),
		).toHaveCount(0);
		await expect(panel.locator('iframe[title="Pickup location map"]')).toHaveCount(
			locations.length,
		);
	});
});
