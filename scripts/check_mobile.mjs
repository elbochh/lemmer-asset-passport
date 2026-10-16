/** Use a local server with an isolated development database and AUTO_GUIDANCE_WORKER=0. */
import { chromium, webkit } from "playwright";
import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";

const base = process.env.MOBILE_TEST_URL || "http://127.0.0.1:5173";
assert(
  ["localhost", "127.0.0.1", "[::1]"].includes(new URL(base).hostname),
  "Use a local test server",
);
const engine = process.env.MOBILE_TEST_ENGINE || "chromium";
assert(["chromium", "webkit"].includes(engine), "Choose chromium or webkit");
const browser = await (engine === "webkit" ? webkit : chromium).launch(
  engine === "chromium"
    ? { channel: process.env.MOBILE_TEST_CHANNEL || "chrome" }
    : {},
);
const directory = `.local/mobile-qa/${engine}`;
await mkdir(directory, { recursive: true });
const context = await browser.newContext({
  viewport: { width: 375, height: 812 },
  isMobile: true,
  hasTouch: true,
});
const page = await context.newPage();
const errors = [],
  checks = [];
page.on("pageerror", (e) => errors.push(e.message));
page.on("response", (response) => {
  // An anonymous session is expected on the welcome and QR sign-in screens.
  if (
    response.status() >= 400 &&
    !(response.status() === 401 && response.url().endsWith("/api/session"))
  )
    errors.push(`${response.status()} ${response.url()}`);
});
async function settled() {
  await page.waitForLoadState("networkidle");
  await page.locator(".loading-page").waitFor({ state: "hidden" });
}
async function layout(label) {
  const measurements = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    content: document.documentElement.scrollWidth,
    alerts: [...document.querySelectorAll(".error-box")].map(
      (e) => e.textContent,
    ),
    clippedControls: [
      ...document.querySelectorAll(
        "main button, main input, main textarea, main select",
      ),
    ]
      .filter((e) => {
        const r = e.getBoundingClientRect();
        return (
          r.width &&
          !e.closest(".tabs, .ai-tabs, .table-scroll") &&
          (r.left < -1 || r.right > document.documentElement.clientWidth + 1)
        );
      })
      .map((e) => e.outerHTML.slice(0, 180)),
  }));
  checks.push({ label, ...measurements });
  assert(
    measurements.content <= measurements.viewport + 1,
    `${label}: horizontal page overflow`,
  );
  assert.deepEqual(measurements.alerts, [], `${label}: error alert`);
  assert.deepEqual(
    measurements.clippedControls,
    [],
    `${label}: control outside the screen`,
  );
}
async function screen(route, width, height = 900) {
  await page.setViewportSize({ width, height });
  await page.goto(base + route);
  await settled();
  await layout(`${route} at ${width}×${height}`);
}
async function screenshot(name) {
  await page.screenshot({ path: `${directory}/${name}.png`, fullPage: true });
}
async function json(path, data) {
  const response = data
    ? await context.request.post(base + "/api" + path, { data })
    : await context.request.get(base + "/api" + path);
  assert(
    response.ok(),
    `${path}: ${response.status()} ${await response.text()}`,
  );
  return response.json();
}
try {
  await screen("/", 320, 568);
  await page.getByRole("button", { name: "Staff / customer sign in" }).click();
  await layout("Sign in dialog at 320px");
  await screenshot("sign-in-320");
  await page.getByRole("button", { name: "Close dialog" }).click();
  await page.getByRole("button", { name: "Open technician workspace" }).click();
  await page.locator(".page-heading").waitFor();
  const session = await json("/session"),
    assets = await json("/assets"),
    dashboard = await json("/dashboard");
  const routes = [
    "/",
    "/my-work",
    "/requests",
    "/assets",
    `/assets/${assets[0].id}`,
    `/requests/${dashboard.requests[0].id}`,
    `/requests/${dashboard.requests[0].id}/receipt`,
    "/catalog",
    "/knowledge",
    "/procedures",
    "/evaluation",
    "/settings",
  ];
  for (const width of [320, 375, 430, 600, 768, 820, 1024, 1280, 1440]) {
    for (const route of routes) await screen(route, width);
    console.log(`PASS technician screens at ${width}px (${engine})`);
  }
  await screen("/requests", 375, 812);
  assert(
    await page
      .getByRole("combobox", { name: "Demo account" })
      .evaluate((e) => e.getBoundingClientRect().height >= 44),
    "The account selector must have a 44px touch target in Safari and Chrome",
  );
  assert.equal(
    await page
      .locator(".request-table tbody tr")
      .first()
      .evaluate((e) => getComputedStyle(e).display),
    "grid",
  );
  await screenshot("requests-375");
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page.waitForFunction(
    () =>
      document.activeElement.getAttribute("aria-label") === "Close navigation",
  );
  assert.equal(await page.locator(".main-shell").getAttribute("inert"), "");
  await page.keyboard.press("Shift+Tab");
  assert.equal(
    await page.evaluate(() =>
      document.activeElement.getAttribute("aria-label"),
    ),
    "Sign out",
  );
  await page.keyboard.press("Tab");
  assert.equal(
    await page.evaluate(() =>
      document.activeElement.getAttribute("aria-label"),
    ),
    "Close navigation",
  );
  await page.waitForTimeout(250); // Let the drawer's 200ms transition finish for its screenshot.
  await screenshot("navigation-375");
  await page.keyboard.press("Escape");
  await page.waitForFunction(
    () =>
      document.activeElement.getAttribute("aria-label") === "Open navigation",
  );
  assert.equal(await page.evaluate(() => document.body.style.overflow), "");
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page
    .getByRole("navigation")
    .getByRole("link", { name: "Asset passports", exact: true })
    .click();
  await page.waitForURL("**/assets");
  await page.waitForFunction(
    () =>
      document.querySelector(".mobile-menu").getAttribute("aria-expanded") ===
      "false",
  );
  await page
    .getByRole("button", { name: "Search equipment or requests" })
    .click();
  await page.getByRole("textbox", { name: "Search workspace" }).fill("LM-1042");
  await page.locator(".search-results a").first().waitFor();
  await layout("Search results at 375px");
  assert.equal(
    await page
      .getByRole("textbox", { name: "Search workspace" })
      .evaluate((e) => getComputedStyle(e).fontSize),
    "16px",
  );
  await screenshot("search-375");
  await page.getByRole("button", { name: "Close dialog" }).click();
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.waitForFunction(
    () => !document.querySelector(".main-shell").inert,
  );
  assert.equal(await page.locator(".sidebar").getAttribute("aria-modal"), null);
  await page.setViewportSize({ width: 320, height: 480 });
  await page.getByRole("button", { name: "Demo help" }).click();
  const modal = await page.locator("dialog").evaluate((e) => ({
    height: e.getBoundingClientRect().height,
    top: e.getBoundingClientRect().top,
    scroll: e.scrollHeight,
    client: e.clientHeight,
  }));
  assert(
    modal.height <= 456 && modal.top >= 0 && modal.scroll > modal.client,
    "Short-screen dialog must stay on screen and scroll",
  );
  await page.locator("dialog").evaluate((e) => {
    e.scrollTop = e.scrollHeight;
  });
  assert(
    await page.getByRole("button", { name: "Close dialog" }).evaluate((e) => {
      const r = e.getBoundingClientRect();
      return r.top >= 0 && r.bottom <= window.innerHeight;
    }),
    "Dialog close control must remain visible after scrolling",
  );
  await screenshot("help-short-screen");
  await page.keyboard.press("Escape");
  await page.locator("dialog").waitFor({ state: "detached" });
  for (const role of ["reception", "superuser", "customer"]) {
    await json("/accounts/switch", {
      name: session.accounts.find((a) => a.role === role).name,
    });
    const roleRoutes =
      role === "customer"
        ? ["/my-assets", "/parts-requests", "/catalog"]
        : role === "superuser"
          ? ["/operations", "/reception", "/registry", "/customers"]
          : ["/reception", "/registry", "/customers", "/parts-requests"];
    if (role === "customer")
      roleRoutes.push(`/my-assets/${(await json("/portal/assets"))[0].id}`);
    for (const width of [320, 375, 768, 1024, 1440])
      for (const route of roleRoutes) await screen(route, width);
    console.log(`PASS ${role} screens (${engine})`);
  }
  await context.clearCookies();
  await screen(`/passport/${session.share}/${assets[0].code}`, 320, 568);
  await screenshot("qr-sign-in-320");
  assert.deepEqual(errors, [], "Unexpected browser or HTTP errors");
  console.log(
    `PASS ${checks.length} layout checks and mobile interactions (${engine})`,
  );
} finally {
  await writeFile(
    `${directory}/results.json`,
    JSON.stringify({ engine, errors, checks }, null, 2),
  );
  await browser.close();
}
