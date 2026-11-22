// End-to-end browser check of the Rust inspection tab (technician → customer).
// Start the backend locally first (see README), then: node scripts/check_rust_inspection.mjs
// Screenshots are written to .local/rust-qa/.
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";

const base = process.env.RUST_TEST_URL || "http://127.0.0.1:8000";
const out = ".local/rust-qa";
mkdirSync(out, { recursive: true });
const errors = [];
const browser = await chromium.launch({
  channel: process.env.RUST_TEST_CHANNEL || "chrome",
});
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
page.on("pageerror", (e) => errors.push("pageerror: " + e.message));
page.on("response", (r) => {
  // Signed-out session probe on the landing page is expected to be 401.
  const expected = r.status() === 401 && r.url().endsWith("/api/session");
  if (r.status() >= 400 && !expected) errors.push(`HTTP ${r.status()} ${r.url()}`);
});
const step = (name) => console.log("PASS", name);
const shot = (name) => page.screenshot({ path: `${out}/${name}.png`, fullPage: true });

await page.goto(base);
await page.getByRole("button", { name: "Open technician workspace" }).click();
await page.locator(".page-heading").waitFor();
await page.getByRole("link", { name: "Rust inspection" }).click();
await page.getByRole("heading", { name: "Rust inspection" }).waitFor();
step("tab visible in technician navigation");
await page.locator(".rust-model").waitFor();
await shot("1-tab");

await page.locator(".rust-vehicle").first().click();
await page.getByRole("heading", { name: "Add a photo" }).waitFor();
step("vehicle opens a bay visit");
await page.locator(".rust-sample").first().click();
await page.locator(".rust-preview").waitFor();
step("sample photo uploaded");
await page.getByRole("button", { name: "Run rust scan" }).click();
await page.locator(".rust-overlay").waitFor();
const regions = await page.locator(".rust-overlay polygon").count();
if (!regions) throw new Error("scan returned no regions on a rusty sample");
step(`scan drew ${regions} region(s)`);
await shot("2-scanned");

await page.getByPlaceholder(/Surface rust/).fill("Checked by hand at the rear arch.");
await page.getByRole("button", { name: "Confirm & record" }).click();
await page.locator(".rust-final").waitFor();
step("technician confirmed; scan locked");
await shot("3-confirmed");

await page.getByRole("link", { name: "Open the vehicle passport" }).click();
await page.locator(".rust-record").first().waitFor();
step("confirmed scan on staff passport timeline");
await shot("4-passport");

// Customer view of the same vehicle.
const options = await page.locator(".demo-account-switch option").allTextContents();
const customer = options.findIndex((o) => o.includes("Customer"));
await page.locator(".demo-account-switch").selectOption({ index: customer });
await page.waitForURL("**/my-assets");
await page.locator("a.catalog-card").filter({ hasText: "VH-1001" }).click();
await page.locator(".rust-record").first().waitFor({ timeout: 10000 });
step("customer sees confirmed scan on their passport");
await shot("5-customer");

// Phone width.
await page.setViewportSize({ width: 375, height: 800 });
await page.locator(".demo-account-switch").selectOption({
  index: options.findIndex((o) => o.includes("Technician")),
});
await page.goto(base + "/rust-scan");
await page.locator(".rust-model").waitFor();
const overflow = await page.evaluate(
  () => document.documentElement.scrollWidth - window.innerWidth,
);
if (overflow > 1) throw new Error(`horizontal overflow ${overflow}px at 375px`);
step("no horizontal overflow at 375px");
await shot("6-phone");

await browser.close();
if (errors.length) {
  console.error(errors.join("\n"));
  process.exit(1);
}
console.log("All rust inspection checks passed. Screenshots in", out);
