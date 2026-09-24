import { expect, test } from "@playwright/test";
import { addToCartViaPDP, fillCheckout, submitCheckout, uniqueBuyer } from "./personas/helpers";

interface PaymentRow {
	method: string;
	label: string;
	advance_amount?: number;
	balance_amount?: number;
}

test.describe("advance payment", () => {
	test("checkout label, split and confirmation follow the shop settings", async ({ page }) => {
		await addToCartViaPDP(page, "ceramic-mug");

		// Gate on the store's own settings: the summary exposes the advance
		// method only when it is enabled, and the row's label and amounts
		// reflect the configured Percent or Flat base against this cart total.
		const summary = await page.request.get(
			"/api/method/shop.storefront.checkout.get_checkout_summary",
		);
		const row = ((await summary.json()).message.payment_methods as PaymentRow[]).find(
			(entry) => entry.method === "advance",
		);
		test.skip(!row, "Advance payment is disabled in Shop Settings");

		await page.goto("/checkout");
		const advance = page.locator('input[name="payment_method"][value="advance"]');
		await expect(advance).toBeVisible();
		// The rendered option must match the settings-derived label exactly —
		// valid for either base, at any percentage or flat amount.
		await expect(page.locator("body")).toContainText(row!.label);

		// Selecting the advance option reveals the bank instructions right at
		// checkout; they render only when the merchant has filled them in.
		const instructions: string | null = await page.evaluate(() => {
			const data = (window as any).page_data || {};
			const value = (data.store || data).advance_instructions;
			return value || null;
		});
		await advance.check();
		const note = page.locator('[data-shop="advance-instructions"]');
		if (instructions) {
			await expect(note).toBeVisible();
			await expect(note).toContainText(instructions);
		} else {
			await expect(note).toBeHidden();
		}

		await fillCheckout(page, uniqueBuyer("advance-e2e"));
		await submitCheckout(page, "advance");
		await page.waitForURL(/order-confirmation/);

		// Confirmation: advance tile (due line + optional bank instructions)
		// and the pending status stage.
		await expect(page.locator("body")).toContainText(/advance due/i);
		await expect(page.locator("body")).toContainText(/advance pending/i);
		await expect(page.locator("body")).toContainText(/on delivery/i);

		const orderId = page.url().match(/order-confirmation\/([^?]+)/)?.[1];
		expect(orderId).toBeTruthy();

		const cookie =
			(await page.context().cookies()).find((c) => c.name === "shop_cart_token")?.value || "";
		const api = await page.request.get(
			`/api/method/shop.storefront.orders.get_order_summary?name=${orderId}&token=${encodeURIComponent(cookie)}`,
		);
		expect(api.ok()).toBeTruthy();
		const info = (await api.json()).message;
		expect(info.payment_method).toBe("advance");

		const block = info.advance_payment;
		expect(block.line).toMatch(/advance due/i);
		expect(block.received).toBe(0);
		expect(block.balance).toBeGreaterThanOrEqual(0);
		// The order must carry the same split the checkout displayed.
		expect(block.advance_amount).toBeCloseTo(row!.advance_amount!, 2);
		// Bank details surface only when the merchant has filled them in.
		if (block.instructions) {
			await expect(page.locator("body")).toContainText(block.instructions);
		}
	});
});
