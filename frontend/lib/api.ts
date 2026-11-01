export type Status = "stored" | "queued" | "processing" | "ready" | "failed";
export type Role = "admin" | "archivist" | "reviewer" | "viewer";
export type Permission = "documents.read" | "documents.upload" | "ocr.run" | "review.write" | "users.manage";
export type DocumentRecord = {
  id: string; filename: string; size_bytes: number; mime_type: string; sha256: string;
  page_count: number; status: Status; status_reason: string; created_at: string; updated_at: string;
};
export type DocumentList = { items: DocumentRecord[]; total: number; limit: number; offset: number };
export type Statistics = { total_documents: number; total_bytes: number; by_status: Record<Status, number> };
export type Health = { status: string; ocr_configured: boolean; ocr_engine: string | null; ocr_languages: string | null;
  max_upload_bytes: number; supported_extensions: string[] };
export type OcrRun = { id: string; document_id: string; status: "queued" | "processing" | "ready" | "failed";
  engine: string; engine_version: string | null; languages: string; params: Record<string, unknown>;
  created_by: string; created_at: string; started_at: string | null; finished_at: string | null; error: string | null;
  pages_total: number; pages_done: number; mean_confidence: number | null; review_required: boolean | null };
export type Processing = { document_id: string; status: Status; reason: string; updated_at: string; ocr_configured: boolean;
  latest_run: OcrRun | null; extracted_text: string | null; ocr_confidence: number | null;
  review_required: boolean | null; classification: string | null };
export type QualityMetrics = { score: number; route: "fast" | "layout" | "advanced"; blank: boolean; skew_angle: number;
  columns: number; has_table: boolean; layout: "simple" | "multi_column" | "tabular"; sharpness: number; contrast: number;
  resolution: number; skew: number; layout_simplicity: number; noise: number; weights: number[] };
export type PageAnalysis = { run_id: string; page_no: number; width: number; height: number; dpi: number | null;
  dpi_source: "metadata" | "rendered" | "estimated_a4"; metrics: QualityMetrics; quality_score: number;
  suggested_route: "fast" | "layout" | "advanced"; blank: boolean; preprocessing: Record<string, unknown>[];
  mean_confidence: number | null; review_required: boolean; text_length: number };
export type OcrSummary = { engine: { configured: boolean; engine: string | null; version: string | null;
  languages: string | null; missing_languages: string[] | null; error: string | null };
  runs: OcrRun[]; run: OcrRun | null; pages: PageAnalysis[] };
export type OcrWord = { text: string; confidence: number | null; box: [number, number, number, number] };
export type OcrLine = { line_no: number; text: string; confidence: number | null;
  box: [number, number, number, number]; words: OcrWord[] };
export type OcrPage = { run_id: string; page: number; analysis: PageAnalysis | null; lines: OcrLine[] };
export type AuditEvent = { sequence: number; action: string; actor: string; timestamp: string };
export type User = { id: string; username: string; display_name: string; role: Role; active: boolean;
  created_at: string; permissions: Permission[] };
export type AuthStatus = { setup_required: boolean; authenticated: boolean };

const base = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
export const apiUrl = (path: string) => `${base}/api${path}`;

/** Raised when the server session is missing or expired; the shell redirects to the sign-in page. */
export class AuthRequired extends Error {}
export const AUTH_EVENT = "smartarchive:auth-required";

function message(body: unknown, fallback: string) {
  if (body && typeof body === "object" && "detail" in body && typeof body.detail === "string") return body.detail;
  return fallback;
}
async function request<T>(method: string, path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetch(apiUrl(path), {
      method, signal, cache: "no-store", credentials: "include",
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new Error("تعذر الاتصال بالخدمة. تأكد من تشغيل الخادم ثم أعد المحاولة.");
  }
  if (response.status === 401 && !path.startsWith("/auth/")) {
    window.dispatchEvent(new Event(AUTH_EVENT));
    throw new AuthRequired("انتهت الجلسة. يرجى تسجيل الدخول.");
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(message(payload, response.status === 404 ? "المستند غير موجود." : "تعذر إكمال الطلب. حاول مرة أخرى."));
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
export const get = <T,>(path: string, signal?: AbortSignal) => request<T>("GET", path, undefined, signal);
export const post = <T,>(path: string, body?: unknown) => request<T>("POST", path, body ?? {});
export const patch = <T,>(path: string, body: unknown) => request<T>("PATCH", path, body);

export function upload(file: File, onProgress: (value: number) => void, signal: AbortSignal): Promise<DocumentRecord> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", apiUrl("/documents"));
    xhr.withCredentials = true;
    xhr.responseType = "json";
    xhr.timeout = 120_000;
    xhr.upload.onprogress = event => { if (event.lengthComputable) onProgress(Math.round(event.loaded * 100 / event.total)); };
    xhr.onload = () => {
      if (xhr.status === 201 && xhr.response?.id) resolve(xhr.response as DocumentRecord);
      else if (xhr.status === 401) { window.dispatchEvent(new Event(AUTH_EVENT)); reject(new AuthRequired("انتهت الجلسة. يرجى تسجيل الدخول.")); }
      else reject(new Error(message(xhr.response, "لم يكتمل حفظ المستند. تحقق من الملف وحاول مجددًا.")));
    };
    xhr.onerror = () => reject(new Error("انقطع الاتصال. تحقق من قائمة المستندات قبل إعادة الرفع."));
    xhr.ontimeout = () => reject(new Error("انتهت مهلة الطلب. تحقق من قائمة المستندات قبل إعادة المحاولة."));
    xhr.onabort = () => reject(new Error("أُلغي الطلب. تحقق من قائمة المستندات إذا كان الإرسال قد اكتمل."));
    const cancel = () => xhr.abort();
    signal.addEventListener("abort", cancel, { once: true });
    xhr.onloadend = () => signal.removeEventListener("abort", cancel);
    const body = new FormData(); body.append("file", file);
    xhr.send(body);
  });
}
