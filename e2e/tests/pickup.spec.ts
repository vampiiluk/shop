import { expect, test } from "@playwright/test";
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
}

test.describe("store pickup", () => {
	test("pickup reveals locations with maps, waives shipping and records the choice", async ({
		page,
	}) => {
		await addToCartViaPDP(page, "ceramic-mug");

		// Gate on the store's own settings: the summary exposes pickup_locations
		// only when pickup is switched on with at least one location.
		const summary = await page.request.get(
			"/api/method/shop.storefront.checkout.get_checkout_summary",
		);
		const message = (await summary.json()).message;
		const locations = (message.pickup_locations || []) as PickupLocation[];
		test.skip(!locations.length, "pickup is not configured in Shop Settings");

		await page.goto("/checkout");
		const pickup = page.locator('input[name="payment_method"][value="pickup"]');
		await expect(pickup).toBeVisible();
		await pickup.check();

		// One card per location, each embedding a map of where to collect.
		const panel = page.locator('[data-shop="pickup-panel"]');
		await expect(panel).toBeVisible();
		await expect(panel.locator('input[name="pickup_location"]')).toHaveCount(locations.length);
		await expect(panel.locator('iframe[src*="openstreetmap.org"]')).toHaveCount(
			locations.length,
		);
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
		await expect(page.locator('iframe[src*="openstreetmap.org"]')).toHaveCount(1);
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
		expect(order.pickup_location?.map_url).toContain("openstreetmap.org");
		const labels = (order.progress as { label: string }[]).map((stage) => stage.label);
		expect(labels).toContain("Pay at pickup");
	});
});
