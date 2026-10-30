import { test, expect } from "@playwright/test";
import fs from "node:fs/promises";
import path from "node:path";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";

test.describe.configure({ mode: "serial" });
const hash = (buffer: Buffer) => createHash("sha256").update(buffer).digest("hex");

test("real Arabic image: upload, persist, preview, download, search and mobile layout", async ({ page }, info) => {
  const source = await fs.readFile(path.resolve(__dirname, "../../data/input/sample.png"));
  await page.goto("/");
  await expect(page.getByTestId("document-count")).toHaveText(/^[0٠]$/);
  await page.getByRole("link", { name: "رفع أول مستند", exact: true }).click();
  await page.locator("#document-file").setInputFiles({ name: "نص عربي.png", mimeType: "image/png", buffer: source });
  const responsePromise = page.waitForResponse(response => response.url().endsWith("/api/documents") && response.request().method() === "POST");
  await page.getByRole("button", { name: "رفع وحفظ المستند", exact: true }).click();
  const response = await responsePromise;
  expect(response.status()).toBe(201);
  const document = await response.json();
  expect(document.sha256).toBe(hash(source));
  await expect(page.getByRole("heading", { name: "تم حفظ المستند", exact: true })).toBeVisible();
  await page.getByRole("link", { name: "عرض المستند", exact: true }).click();
  await expect(page.getByRole("heading", { name: "نص عربي.png", exact: true })).toBeVisible();
  await expect.poll(() => page.getByAltText("معاينة نص عربي.png").evaluate(element => {
    const image = element as HTMLImageElement; return image.complete && image.naturalWidth > 0;
  })).toBe(true);
  await page.screenshot({ path: info.outputPath("document-detail.png"), fullPage: true });
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("link", { name: "تنزيل الأصل", exact: true }).click();
  const download = await downloadPromise;
  const target = info.outputPath("downloaded-original.png");
  await download.saveAs(target);
  expect(hash(await fs.readFile(target))).toBe(hash(source));
  await page.getByRole("button", { name: "تحديث السجل", exact: true }).click();
  await expect(page.getByText("طلب تنزيل الأصل", { exact: true })).toBeVisible();
  await page.locator("nav").getByRole("link", { name: "المستندات", exact: true }).click();
  await page.getByRole("textbox", { name: "اسم المستند", exact: true }).fill("نص عربي");
  await page.getByRole("button", { name: "بحث", exact: true }).click();
  await expect(page.getByRole("link", { name: /نص عربي.png image\/png/ })).toBeVisible();
  await page.getByLabel("تصفية النوع", { exact: true }).selectOption("pdf");
  await expect(page.getByRole("heading", { name: "لا توجد نتائج مطابقة", exact: true })).toBeVisible();
  await page.getByLabel("تصفية النوع", { exact: true }).selectOption("image");
  await expect(page.getByRole("link", { name: /نص عربي.png image\/png/ })).toBeVisible();
  await page.locator("nav").getByRole("link", { name: "لوحة التحكم", exact: true }).click();
  await expect(page).toHaveURL("http://127.0.0.1:3001/");
  await page.reload();
  await expect(page.getByTestId("document-count")).toHaveText(/^[1١]$/);
  await page.screenshot({ path: info.outputPath("dashboard-desktop.png"), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("button", { name: "فتح القائمة", exact: true })).toBeVisible();
  await page.screenshot({ path: info.outputPath("dashboard-mobile.png"), fullPage: true });
  if (await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)) {
    console.log(await page.evaluate(() => ({
      viewport: window.innerWidth, root: document.documentElement.scrollWidth,
      elements: ["html", "body", ".app-frame", ".main-column", ".page-content", ".table-scroll", "table", ".sidebar"].map(selector => {
        const el = document.querySelector(selector) as HTMLElement;
        const rect = el.getBoundingClientRect();
        return { selector, left: rect.left, right: rect.right, width: rect.width, scroll: el.scrollWidth,
          overflow: getComputedStyle(el).overflowX, display: getComputedStyle(el).display };
      }),
    })));
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.getByRole("button", { name: "فتح القائمة", exact: true }).click();
  await expect(page.locator("nav").getByRole("link", { name: "المستندات", exact: true })).toBeVisible();
});

test("API failure shows an error rather than fabricated statistics", async ({ page }) => {
  await page.route("**/api/statistics", route => route.abort());
  await page.goto("/");
  await expect(page.getByRole("alert").filter({ hasText: "تعذر الاتصال بالخدمة" })).toBeVisible();
  await expect(page.getByTestId("document-count")).toHaveCount(0);
});

test("unsupported upload is rejected before sending it", async ({ page }) => {
  await page.goto("/upload");
  await page.locator("#document-file").setInputFiles({ name: "invalid.html", mimeType: "text/html", buffer: Buffer.from("<html></html>") });
  await expect(page.getByRole("alert").filter({ hasText: "اختر ملف PDF" })).toBeVisible();
  await expect(page.getByRole("button", { name: "رفع وحفظ المستند", exact: true })).toBeDisabled();
});

test("PDF upload exposes its unchanged original and browser preview", async ({ page }, info) => {
  const python = process.env.SMARTARCHIVE_TEST_PYTHON || path.resolve(__dirname, "../../.venv/Scripts/python.exe");
  const source = execFileSync(python, ["-c", "import pymupdf,sys; d=pymupdf.open(); p=d.new_page(); p.insert_text((72,72),'SmartArchive-X PDF test'); sys.stdout.buffer.write(d.tobytes()); d.close()"]);
  await page.goto("/upload");
  await page.locator("#document-file").setInputFiles({ name: "synthetic-preview.pdf", mimeType: "application/pdf", buffer: source });
  await page.getByRole("button", { name: "رفع وحفظ المستند", exact: true }).click();
  await page.getByRole("link", { name: "عرض المستند", exact: true }).click();
  await expect(page.getByRole("heading", { name: "synthetic-preview.pdf", exact: true })).toBeVisible();
  await expect.poll(() => page.locator(".preview-surface img").evaluate(element => {
    const image = element as HTMLImageElement; return image.complete && image.naturalWidth > 0;
  })).toBe(true);
  await page.screenshot({ path: info.outputPath("pdf-preview.png"), fullPage: true });
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("link", { name: "تنزيل الأصل", exact: true }).click();
  const download = await downloadPromise;
  const target = info.outputPath("unchanged.pdf");
  await download.saveAs(target);
  expect(hash(await fs.readFile(target))).toBe(hash(source));
});
