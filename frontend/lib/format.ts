import type { Status } from "./api";
export const statuses: Record<Status, string> = {
  stored: "محفوظ", queued: "في الانتظار", processing: "قيد المعالجة", ready: "معالَج", failed: "تعذرت المعالجة",
};
export const number = (value: number) => new Intl.NumberFormat("ar").format(value);
export const date = (value: string) => new Intl.DateTimeFormat("ar", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
export function bytes(value: number) {
  if (value < 1024) return `${number(value)} بايت`;
  if (value < 1024 * 1024) return `${number(Math.round(value / 1024))} كيلوبايت`;
  return `${new Intl.NumberFormat("ar", { maximumFractionDigits: 1 }).format(value / 1024 / 1024)} ميجابايت`;
}
export const reasons: Record<string, string> = {
  OCR_NOT_CONFIGURED: "محرك OCR غير مهيأ على الخادم",
  OCR_NOT_REQUESTED: "لم تُطلب المعالجة بعد",
  OCR_QUEUED: "بانتظار دورها في المعالجة",
  OCR_REQUEUED: "أُعيدت إلى قائمة الانتظار بعد توقف الخادم",
  OCR_RUNNING: "فحص الجودة واستخراج النص جارٍ",
  OCR_COMPLETED: "اكتمل استخراج النص",
  REVIEW_REQUIRED: "اكتمل الاستخراج ويحتاج مراجعة بشرية",
  REVIEW_COMPLETED: "اكتمل الاستخراج وروجعت الصفحات المشكوك فيها",
  OCR_FAILED: "تعذرت المعالجة",
};
export const percent = (value: number | null | undefined) =>
  value === null || value === undefined ? "—" : new Intl.NumberFormat("ar", { style: "percent", maximumFractionDigits: 0 }).format(value);
export const decimal = (value: number, digits = 2) => new Intl.NumberFormat("ar", { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(value);
export const actors = (actor: string) => actor === "local" ? "جلسة محلية" : actor === "system:ocr" ? "المعالجة الآلية" : actor === "system:classifier" ? "التصنيف الآلي" : actor;
export const categoryStates = { confirmed: "معتمد", suggested: "مقترح", uncertain: "غير مؤكد", none: "غير مصنّف" } as const;
export const suggestionOutcomes: Record<string, string> = {
  suggested: "اقتراح بثقة كافية", weak_evidence: "الأدلة ضعيفة (كلمة واحدة أو أقل من الحد)",
  ambiguous: "أكثر من فئة متقاربة", group_only: "المجموعة واضحة والنوع غير مؤكد", no_keywords: "لا توجد كلمات مفتاحية معروفة في النص", no_text: "لا يوجد نص",
};
export const sources = { ocr: "نص آلي (OCR)", review: "نص مُراجَع بشريًا" } as const;

/** The same folding as the server's search (search/arabic.py): no diacritics or tatweel, one alef, ى→ي, ة→ه,
 * Arabic-Indic and Persian digits as ASCII. Used to outline the lines of a page that hold a query's words. */
export function normalizeArabic(text: string) {
  return text.normalize("NFC")
    .replace(/[\u064B-\u065F\u0670\u0640\u06D6-\u06ED\u200B-\u200F\u061C\uFEFF]/g, "")
    .replace(/[\u0623\u0625\u0622\u0671]/g, "\u0627").replace(/\u0649/g, "\u064A").replace(/\u0629/g, "\u0647")
    .replace(/\u0624/g, "\u0648").replace(/\u0626/g, "\u064A")
    .replace(/[\u0660-\u0669]/g, d => String(d.charCodeAt(0) - 0x0660))
    .replace(/[\u06F0-\u06F9]/g, d => String(d.charCodeAt(0) - 0x06F0))
    .toLowerCase();
}

export function matchWords(line: string, query: string) {
  const text = normalizeArabic(line);
  return normalizeArabic(query).split(/[\s،,؛;:]+/).some(word => (word.length >= 3 || /^\d{2,}$/.test(word)) && text.includes(word));
}
