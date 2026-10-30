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
