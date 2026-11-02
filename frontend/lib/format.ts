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
export const actors = (actor: string) => actor === "local" ? "جلسة محلية" : actor === "system:ocr" ? "المعالجة الآلية" : actor;
export const sources = { ocr: "نص آلي (OCR)", review: "نص مُراجَع بشريًا" } as const;
