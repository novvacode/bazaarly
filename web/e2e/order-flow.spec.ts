import { expect, test } from "@playwright/test";

/**
 * SPEC §19 scenario: owner signs up and builds a menu → customer places a COD order →
 * owner moves it to completed on the board → tracking page shows completed.
 */
test("owner to customer to owner: a COD pickup order end to end", async ({ page, browser }) => {
  const id = Date.now().toString(36);
  const slug = `e2e-${id}`;

  // 1. Owner signs up and adds a category and an item.
  await page.goto("/signup");
  await page.getByLabel("Your name").fill("E2E Owner");
  await page.getByLabel("Email").fill(`owner-${id}@example.com`);
  await page.getByLabel("Password").fill("correct-horse-battery");
  await page.getByLabel("Business name").fill(`E2E Bakery ${id}`);
  await page.getByLabel("Store link").fill(slug);
  await page.getByRole("button", { name: "Create store" }).click();
  await page.waitForURL("**/dashboard/settings");

  await page.goto("/dashboard/menu");
  await page.getByRole("button", { name: "Category" }).click();
  await page.getByLabel("Category name").fill("Cakes");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("heading", { name: "Cakes" })).toBeVisible();

  await page.getByRole("button", { name: "Item", exact: true }).click();
  await page.getByLabel("Name").fill("Mango Cheesecake");
  await page.getByLabel("Price (₹)").fill("450");
  await page.getByLabel("Category").selectOption({ label: "Cakes" });
  await page.getByRole("button", { name: "Add item" }).click();
  await expect(page.getByText("Mango Cheesecake")).toBeVisible();

  // 2. A customer (fresh browser, phone-sized) places a COD order.
  const customer = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const shop = await customer.newPage();
  await shop.goto(`/b/${slug}`);
  await shop.getByRole("button", { name: "Add Mango Cheesecake" }).click();
  await shop.getByRole("button", { name: "Add one Mango Cheesecake" }).click();
  await shop.getByRole("button", { name: /View cart/ }).click();
  await shop.getByRole("link", { name: "Checkout" }).click();
  await shop.getByLabel("Name").fill("Priya");
  await shop.getByLabel("Mobile number").fill("9876543210");
  await shop.getByRole("button", { name: /Place order/ }).click();
  await shop.waitForURL("**/o/**");
  await expect(shop.getByTestId("tracking-headline")).toContainText("Order received");
  const trackingUrl = shop.url();

  // 3. The owner sees it on the board and moves it to completed.
  await page.goto("/dashboard");
  const card = page.getByTestId("board-card").filter({ hasText: "Priya" });
  await expect(card).toBeVisible({ timeout: 20_000 });
  await card.click();
  const detail = page.getByTestId("order-detail");
  for (const action of ["Confirm", "Start preparing", "Ready for pickup", "Complete"]) {
    await detail.getByRole("button", { name: action, exact: true }).click();
    await expect(detail.getByRole("button", { name: action, exact: true })).toBeHidden();
  }
  await expect(detail.getByText("Completed").first()).toBeVisible();

  // 4. The customer's tracking page shows completed.
  await shop.goto(trackingUrl);
  await expect(shop.getByTestId("tracking-headline")).toContainText("Completed");
  await customer.close();
});

test("storefront assistant answers from the menu @mobile", async ({ page }) => {
  await page.goto("/b/demo-bakery");
  await page.getByRole("button", { name: "Ask a question" }).click();
  await page.getByLabel("Your question").fill("Is the chocolate truffle cake eggless?");
  await page.getByRole("button", { name: "Send" }).click();
  const log = page.getByTestId("chat-log");
  await expect(log).toContainText("Is the chocolate truffle cake eggless?");
  // With LLM_PROVIDER=fake the reply quotes the best-matching menu chunk.
  await expect(log).toContainText("₹650", { timeout: 20_000 });
});
