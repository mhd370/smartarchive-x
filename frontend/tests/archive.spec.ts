import { test, expect, type Page } from "@playwright/test";
import fs from "node:fs/promises";
import path from "node:path";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";

test.describe.configure({ mode: "serial" });
const hash = (buffer: Buffer) => createHash("sha256").update(buffer).digest("hex");
const ADMIN = { name: "مدير الاختبار", username: "e2e-admin", password: "e2e-password-1" };

/** Fresh storage per run: the first visit creates the admin account, later ones sign in. */
async function signIn(page: Page) {
  await page.goto("/login");
  const setup = page.getByRole("heading", { name: "إعداد حساب المدير", exact: true });
  const login = page.getByRole("heading", { name: "تسجيل الدخول", exact: true });
  await expect(setup.or(login)).toBeVisible();
  if (await setup.isVisible()) {
    await page.getByLabel("الاسم الظاهر", { exact: true }).fill(ADMIN.name);
    await page.getByLabel("اسم المستخدم", { exact: true }).fill(ADMIN.username);
    await page.getByLabel("كلمة المرور", { exact: true }).fill(ADMIN.password);
    await page.getByLabel("تأكيد كلمة المرور", { exact: true }).fill(ADMIN.password);
    await page.getByRole("button", { name: "إنشاء الحساب والدخول", exact: true }).click();
  } else {
    await page.getByLabel("اسم المستخدم", { exact: true }).fill(ADMIN.username);
    await page.getByLabel("كلمة المرور", { exact: true }).fill(ADMIN.password);
    await page.getByRole("button", { name: "دخول", exact: true }).click();
  }
  await expect(page).toHaveURL("http://127.0.0.1:3001/");
  await expect(page.getByText(ADMIN.name, { exact: true })).toBeVisible();
}

test("signed-out visitor is sent to sign-in and nothing is exposed", async ({ page }) => {
  await page.goto("/documents");
  await expect(page).toHaveURL(/\/login\?next=%2Fdocuments/);
  await expect(page.getByRole("navigation", { name: "التنقل الرئيسي" })).toHaveCount(0);
});

test("real Arabic image: upload, OCR, quality, preview, download, search and mobile layout", async ({ page }, info) => {
  test.setTimeout(240_000);
  const source = await fs.readFile(path.resolve(__dirname, "../../data/input/sample.png"));
  await signIn(page);
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
  // Real Tesseract run: wait for completion, then quality, extracted lines and their page boxes.
  await expect(page.getByText(/^(اكتمل استخراج النص|اكتمل الاستخراج ويحتاج مراجعة بشرية)$/)).toBeVisible({ timeout: 180_000 });
  await expect(page.getByRole("heading", { name: "جودة الصفحة 1", exact: true }).or(page.getByRole("heading", { name: "جودة الصفحة ١", exact: true }))).toBeVisible();
  await expect(page.locator(".quality-score")).toContainText("Q =");
  await expect(page.locator(".ocr-lines li").first()).toBeVisible();
  expect(await page.locator(".ocr-box").count()).toBe(await page.locator(".ocr-lines li").count());
  await page.locator(".ocr-lines button").first().hover();
  await expect(page.locator(".ocr-box.focused")).toHaveCount(1);
  await page.screenshot({ path: info.outputPath("document-detail.png"), fullPage: true });
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("link", { name: "تنزيل الأصل", exact: true }).click();
  const download = await downloadPromise;
  const target = info.outputPath("downloaded-original.png");
  await download.saveAs(target);
  expect(hash(await fs.readFile(target))).toBe(hash(source));
  await page.getByRole("button", { name: "تحديث السجل", exact: true }).click();
  await expect(page.getByText("طلب تنزيل الأصل", { exact: true })).toBeVisible();
  await expect(page.getByText("اكتمال استخراج النص", { exact: true })).toBeVisible();
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

test("extracted Arabic text is searchable and a correction becomes the searchable text", async ({ page }, info) => {
  test.setTimeout(120_000);
  await signIn(page);
  await page.goto("/documents?q=" + encodeURIComponent("نص عربي"));
  await page.getByRole("link", { name: /نص عربي.png image\/png/ }).first().click();
  await expect(page.locator(".ocr-lines .line-text").first()).toBeVisible({ timeout: 60_000 });
  const lines = await page.locator(".ocr-lines .line-text").allTextContents();
  const words = lines.join(" ").match(/[\u0621-\u064A]{3,}/g) ?? [];
  expect(words.length).toBeGreaterThan(0);
  const word = words.reduce((longest, item) => item.length > longest.length ? item : longest);

  const box = page.getByRole("textbox", { name: "بحث في نصوص المستندات وأسمائها", exact: true });
  await box.fill(word);
  await box.press("Enter");
  await expect(page).toHaveURL(/\/search\?q=/);
  const result = page.locator(".search-result").filter({ hasText: "نص عربي.png" });
  await expect(result).toBeVisible();
  await expect(result.locator("mark").first()).toBeVisible();
  await expect(result.locator(".source-tag").first()).toHaveText("نص آلي (OCR)");
  await page.screenshot({ path: info.outputPath("search-results.png"), fullPage: true });

  await result.getByRole("link", { name: /الصفحة/ }).first().click();
  await page.getByRole("button", { name: "تصحيح النص", exact: true }).click();
  const editor = page.getByLabel("نص الصفحة بعد التصحيح", { exact: true });
  const original = await editor.inputValue();
  await editor.fill("مستند مصحح للاختبار\n" + original);
  await page.getByLabel("ملاحظة (اختيارية)", { exact: true }).fill("اختبار آلي");
  await page.getByRole("button", { name: "حفظ التصحيح", exact: true }).click();
  await expect(page.getByText(/حُفظ التصحيح كنسخة/)).toBeVisible();
  await expect(page.locator(".review-panel .source-tag")).toHaveText("نص مُراجَع بشريًا");
  await page.screenshot({ path: info.outputPath("page-reviewed.png"), fullPage: true });
  await page.getByRole("button", { name: "تحديث السجل", exact: true }).click();
  await expect(page.getByText("تصحيح نص صفحة ومراجعتها", { exact: true })).toBeVisible();

  await page.goto("/search?q=" + encodeURIComponent("مصحح للاختبار"));
  const corrected = page.locator(".search-result").filter({ hasText: "نص عربي.png" });
  await expect(corrected.locator(".source-tag").first()).toHaveText("نص مُراجَع بشريًا");
  await page.goto("/review");
  await expect(page.getByRole("heading", { name: "صفحات بانتظار المراجعة", exact: true })).toBeVisible();
});

test("a person classifies a document, and the category filters documents", async ({ page }, info) => {
  test.setTimeout(90_000);
  await signIn(page);
  await page.goto("/documents?q=" + encodeURIComponent("نص عربي"));
  await page.getByRole("link", { name: /نص عربي.png image\/png/ }).first().click();
  const panel = page.locator(".classification-panel");
  await expect(panel.getByRole("heading", { name: "التصنيف", exact: true })).toBeVisible();
  await expect(panel.getByText(/اقتراح النظام/)).toBeVisible({ timeout: 30_000 });
  await panel.getByRole("button", { name: /اختيار فئة أخرى|إعادة التصنيف/ }).click();
  await panel.getByLabel("الفئة", { exact: true }).selectOption("report");
  const reason = panel.getByLabel(/السبب/);
  await reason.fill("اختبار آلي للتصنيف");
  await panel.getByRole("button", { name: "حفظ التصنيف", exact: true }).click();
  await expect(panel.locator(".category-confirmed")).toHaveText("تقرير");
  await expect(panel.getByText(/اعتمده/)).toBeVisible();
  await page.screenshot({ path: info.outputPath("classification.png"), fullPage: true });

  await page.goto("/documents?category=report");
  await expect(page.getByRole("link", { name: /نص عربي.png image\/png/ })).toBeVisible();
  await expect(page.locator("td .category-confirmed").first()).toHaveText("تقرير");
  await page.goto("/documents?category=contract");
  await expect(page.getByRole("heading", { name: "لا توجد نتائج مطابقة", exact: true })).toBeVisible();
  await page.goto("/categories");
  await expect(page.getByRole("heading", { name: "فئات المستندات", exact: true })).toBeVisible();
  await expect(page.locator(".category-list > li").filter({ hasText: "تقرير" }).getByRole("link", { name: /معتمد/ })).toBeVisible();
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "توزيع التصنيفات", exact: true })).toBeVisible();
});

test("admin backs up, verifies and checks integrity; evaluation shows measured rates", async ({ page }, info) => {
  test.setTimeout(90_000);
  await signIn(page);
  await page.goto("/system");
  await expect(page.getByRole("heading", { name: "النظام والنسخ الاحتياطي", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "إنشاء نسخة احتياطية", exact: true }).click();
  const row = page.locator("tbody tr").first();
  await expect(row.locator(".backup-name")).toHaveText(/^smartarchive-backup-.*\.zip$/);
  await row.getByRole("button", { name: "تحقق", exact: true }).click();
  await expect(row.getByText("سليمة", { exact: true })).toBeVisible();
  const downloadPromise = page.waitForEvent("download");
  await row.getByRole("link", { name: "تنزيل", exact: true }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/^smartarchive-backup-.*\.zip$/);
  await page.getByRole("button", { name: "تشغيل الفحص", exact: true }).click();
  await expect(page.getByText(/الأرشيف سليم/)).toBeVisible({ timeout: 30_000 });
  await page.screenshot({ path: info.outputPath("system.png"), fullPage: true });

  await page.goto("/evaluation");
  // Metrics are computed on request from every corrected page; allow time on a slow machine.
  await expect(page.getByRole("heading", { name: "تقييم النظام على بيانات الأرشيف", exact: true })).toBeVisible({ timeout: 60_000 });
  await expect(page.getByTestId("micro-cer")).not.toHaveText("—");
  // The test document was a poem: the classifier abstained, so accuracy is undefined but the label is counted.
  await expect(page.locator(".confusion")).toContainText("امتنع");
  await page.screenshot({ path: info.outputPath("evaluation.png"), fullPage: true });
});

test("API failure shows an error rather than fabricated statistics", async ({ page }) => {
  await signIn(page);
  await page.route("**/api/statistics", route => route.abort());
  await page.goto("/");
  await expect(page.getByRole("alert").filter({ hasText: "تعذر الاتصال بالخدمة" })).toBeVisible();
  await expect(page.getByTestId("document-count")).toHaveCount(0);
});

test("unsupported upload is rejected before sending it", async ({ page }) => {
  await signIn(page);
  await page.goto("/upload");
  await page.locator("#document-file").setInputFiles({ name: "invalid.html", mimeType: "text/html", buffer: Buffer.from("<html></html>") });
  await expect(page.getByRole("alert").filter({ hasText: "اختر ملف PDF" })).toBeVisible();
  await expect(page.getByRole("button", { name: "رفع وحفظ المستند", exact: true })).toBeDisabled();
});

test("PDF upload exposes its unchanged original and browser preview", async ({ page }, info) => {
  const python = process.env.SMARTARCHIVE_TEST_PYTHON || path.resolve(__dirname, "../../.venv/Scripts/python.exe");
  const source = execFileSync(python, ["-c", "import pymupdf,sys; d=pymupdf.open(); p=d.new_page(); p.insert_text((72,72),'SmartArchive-X PDF test'); sys.stdout.buffer.write(d.tobytes()); d.close()"]);
  await signIn(page);
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
