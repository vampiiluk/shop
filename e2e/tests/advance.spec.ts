import { expect, test } from "@playwright/test";
import { addToCartViaPDP, fillCheckout, submitCheckout, uniqueBuyer } from "./personas/helpers";

test.describe("advance payment", () => {
	test("checkout offers the advance split and the confirmation explains the balance", async ({
		page,
	}) => {
		await addToCartViaPDP(page, "ceramic-mug");

		const summary = await page.request.get(
			"/api/method/shop.storefront.checkout.get_checkout_summary",
		);
		const methods = (
			(await summary.json()).message.payment_methods as Array<{ method: string }>
		).map((row) => row.method);
		test.skip(!methods.includes("advance"), "Advance payment is disabled on this store");

		await page.goto("/checkout");
		const advance = page.locator('input[name="payment_method"][value="advance"]');
		await expect(advance).toBeVisible();
		// The label carries the split: what is due now versus on delivery.
		await expect(page.locator("body")).toContainText(/advance payment/i);
		await expect(page.locator("body")).toContainText(/on delivery/i);

		const buyer = { ...uniqueBuyer("advance-e2e"), phone: String(Date.now()).slice(-10) };
		await fillCheckout(page, buyer);
		await submitCheckout(page, "advance");
		await page.waitForURL(/order-confirmation/);

		// Confirmation: advance tile with amount due + courier balance, pending stage.
		await expect(page.locator("body")).toContainText(/advance payment/i);
		await expect(page.locator("body")).toContainText(/advance due/i);
		await expect(page.locator("body")).toContainText(/advance pending/i);
		await expect(page.locator("body")).toContainText(/on delivery/i);

		const orderId = page.url().match(/order-confirmation\/([^?]+)/)?.[1];
		expect(orderId).toBeTruthy();

		const api = await page.request.get(
			`/api/method/shop.storefront.orders.get_order_summary?name=${orderId}&token=${(
				await page.context().cookies()
			)
				.find((cookie) => cookie.name === "shop_cart_token")
				?.value || ""}`,
		);
		expect(api.ok()).toBeTruthy();
		const summaryData = (await api.json()).message;
		expect(summaryData.payment_method).toBe("advance");
		expect(summaryData.advance_payment.line).toMatch(/advance due/i);
		expect(summaryData.advance_payment.balance).toBeGreaterThan(0);
		expect(summaryData.advance_payment.received).toBe(0);
	});
});
