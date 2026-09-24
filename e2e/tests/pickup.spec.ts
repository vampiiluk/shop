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

async function checkoutSummary(page: {
	request: import("@playwright/test").APIRequestContext;
}): Promise<{ pickup_locations?: PickupLocation[]; default_pickup_location?: string | null }> {
	const summary = await page.request.get(
		"/api/method/shop.storefront.checkout.get_checkout_summary",
	);
	return (await summary.json()).message;
}

async function configuredLocations(
	page: { request: import("@playwright/test").APIRequestContext },
): Promise<PickupLocation[]> {
	return ((await checkoutSummary(page)).pickup_locations || []) as PickupLocation[];
}

test.describe("store pickup", () => {
	test("pickup reveals locations with maps, waives shipping and records the choice", async ({
		page,
	}) => {
		await addToCartViaPDP(page, "ceramic-mug");

		// Gate on the store's own settings: the summary exposes pickup_locations
		// only when pickup is switched on with at least one location.
		const summary = await checkoutSummary(page);
		const locations = (summary.pickup_locations || []) as PickupLocation[];
		const defaultName = (summary.default_pickup_location || "").trim();
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

		// When Settings names a default location its radio comes pre-checked;
		// with no default configured nothing is chosen for the shopper.
		const checked = panel.locator('input[name="pickup_location"]:checked');
		if (defaultName) {
			await expect(checked).toHaveCount(1);
			expect(await checked.inputValue()).toBe(defaultName);
		} else {
			await expect(checked).toHaveCount(0);
		}

		// Submitting without a location stays on checkout with an explanation —
		// clear the pre-checked default first so nothing is chosen.
		await fillCheckout(page, BUYER);
		await page.evaluate(() => {
			document
				.querySelectorAll<HTMLInputElement>(
					'[data-shop="pickup-panel"] input[name="pickup_location"]',
				)
				.forEach((radio) => (radio.checked = false));
		});
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
		// The pill keeps its own look: Builder's text-block reset.css would
		// otherwise underline it and strip its background.
		const dirStyle = await dirLinks.first().evaluate((el) => {
			const cs = getComputedStyle(el);
			return { decoration: cs.textDecorationLine, background: cs.backgroundColor };
		});
		expect(dirStyle.decoration).not.toContain("underline");
		expect(dirStyle.background).not.toBe("rgba(0, 0, 0, 0)");
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

		// Zoom controls rewrite the embed URL symmetrically around the pin:
		// the view changes while the centre (marker / q) never moves.
		const mapFrame = panel.locator('[data-shop="map-frame"]').first();
		const zoomFrame = mapFrame.locator('iframe[title="Pickup location map"]');
		const centreOf = (src: string) => {
			const url = new URL(src);
			return url.searchParams.get("marker") ?? url.searchParams.get("q");
		};
		const srcBefore = (await zoomFrame.getAttribute("src")) || "";
		await mapFrame.locator('[data-shop="map-zoom"][data-delta="1"]').click();
		await expect.poll(() => zoomFrame.getAttribute("src")).not.toBe(srcBefore);
		const srcZoomedIn = (await zoomFrame.getAttribute("src")) || "";
		expect(centreOf(srcZoomedIn)).toBe(centreOf(srcBefore));
		await mapFrame.locator('[data-shop="map-zoom"][data-delta="-1"]').click();
		await expect.poll(() => zoomFrame.getAttribute("src")).not.toBe(srcZoomedIn);
		expect(centreOf((await zoomFrame.getAttribute("src")) || "")).toBe(centreOf(srcBefore));

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
