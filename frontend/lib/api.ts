export type Status = "stored" | "queued" | "processing" | "ready" | "failed";
export type Role = "admin" | "archivist" | "reviewer" | "viewer";
export type Permission = "documents.read" | "documents.upload" | "ocr.run" | "review.write" | "users.manage";
export type DocumentRecord = {
  id: string; filename: string; size_bytes: number; mime_type: string; sha256: string;
  page_count: number; status: Status; status_reason: string; created_at: string; updated_at: string;
  category_id?: string | null; category_name?: string | null; category_state?: CategoryState | null;
  folder_id?: string | null; folder_path?: string | null;
};
export type DocumentList = { items: DocumentRecord[]; total: number; limit: number; offset: number };
export type Statistics = { total_documents: number; total_bytes: number; by_status: Record<Status, number>;
  pages_pending_review: number; pages_reviewed: number;
  classification: Record<CategoryState, number>;
  categories: { id: string; name: string; confirmed: number; suggested: number }[] };
export type Health = { status: string; ocr_configured: boolean; ocr_engine: string | null; ocr_languages: string | null;
  max_upload_bytes: number; supported_extensions: string[] };
export type OcrRun = { id: string; document_id: string; status: "queued" | "processing" | "ready" | "failed";
  engine: string; engine_version: string | null; languages: string; params: Record<string, unknown>;
  created_by: string; created_at: string; started_at: string | null; finished_at: string | null; error: string | null;
  pages_total: number; pages_done: number; mean_confidence: number | null; review_required: boolean | null };
export type Processing = { document_id: string; status: Status; reason: string; updated_at: string; ocr_configured: boolean;
  latest_run: OcrRun | null; extracted_text: string | null; ocr_confidence: number | null;
  review_required: boolean | null; pending_review_pages: number; classification: string | null };
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
export type TextSource = "ocr" | "review";
export type BackupItem = { name: string; size_bytes: number; modified_at: string; created_at?: string; created_by?: string;
  app_version?: string; schema_version?: number; document_count?: number; original_bytes?: number; unreadable?: boolean };
export type BackupVerification = { name: string; ok: boolean; problems: string[]; problem_count?: number; documents?: number };
export type IntegrityReport = { ok: boolean; warnings: number; checked_at: string; checked_by: string; documents_checked: number;
  database: string; foreign_key_violations: number; document_problems: { document_id: string; filename: string; problem: string }[];
  orphan_folders: string[]; partial_uploads: string[]; missing_triggers: string[]; unindexed_documents: number };
export type OcrEvalPage = { document_id: string; filename: string; page_no: number; ocr_confidence: number | null;
  cer: number | null; wer: number | null; char_errors: number; chars: number; word_errors: number; words: number };
export type EvaluationReport = { generated_at: string;
  ocr: { policy: string; note: string; truncated: boolean; pages: OcrEvalPage[];
    summary: { pages: number; chars: number; words: number; micro_cer: number | null; micro_wer: number | null; macro_cer: number | null };
    by_confidence: { bucket: string; confidence_from: number; confidence_to: number; pages: number; micro_cer: number | null }[] };
  classification: { method: string; note: string; names: Record<string, string>;
    summary: { labelled: number; skipped_without_suggestion: number; covered: number; coverage: number | null;
      accuracy_when_suggested: number | null; accuracy_overall: number | null; macro_f1: number | null };
    per_category: { category_id: string; name: string; support: number; predicted: number; precision: number | null;
      recall: number | null; f1: number | null }[];
    confusion: Record<string, Record<string, number>> } };
export type CategoryState = "confirmed" | "suggested" | "uncertain" | "none";
export type Folder = { id: string; parent_id: string | null; name: string; path: string; created_by: string;
  created_at: string; documents: number; total_documents: number; depth: number };
export type CategoryGroup = { id: string; name: string; categories: number };
export type MetadataField = { field: string; value: string | null; normalized: string | null; source: "extracted" | "human" | null;
  confidence: number | null; page_no: number | null; actor: string | null; updated_at: string | null;
  extracted_value: string | null; protected: boolean; history: number };
export type MetadataResult = { document_id: string; method: string; extracted: boolean; fields: Record<string, MetadataField> };
export type Relation = { id: string; source_id: string; target_id: string; other_id: string; kind: "exact_duplicate" | "near_duplicate" | "version_of";
  score: number; method: string; evidence: Record<string, unknown>; status: "suggested" | "confirmed" | "rejected";
  created_at: string; reviewed_by: string | null; other_filename: string | null; other_created_at: string | null; direction: "newer" | "older" };
export type Category = { group_id?: string | null; group_name?: string | null; id: string; name: string; description: string; keywords: string[]; active: boolean;
  created_by: string; created_at: string; updated_at: string; confirmed: number; suggested: number };
export type KeywordHit = { keyword: string; count: number; heading: boolean; filename: boolean; points: number };
export type ClassificationRecord = { sequence: number; id: string; document_id: string; kind: "suggestion" | "decision";
  category_id: string | null; category_name: string | null; confidence: number | null; method: string;
  scores: Record<string, number> | null; evidence: Record<string, KeywordHit[]> | null;
  basis: Record<string, unknown>; reason: string; actor: string; created_at: string };
export type Classification = { document_id: string; state: CategoryState; category_id: string | null;
  category_name: string | null; sequence: number; suggestion: ClassificationRecord | null;
  decision: ClassificationRecord | null; history: ClassificationRecord[]; reclassification: Reclassification | null };
export type Reclassification = { method: string; from_category_id: string; to_category_id: string; share: number;
  current_share: number; delta: number; min_confidence: number; min_delta: number; suggestion_id: string;
  suggestion_sequence: number; suggested_at: string };
export type ReclassificationQueue = { items: (Reclassification & { document_id: string; filename: string; created_at: string;
  from_category_name: string | null; to_category_name: string | null })[]; total: number; limit: number; offset: number;
  method: string; min_confidence: number; min_delta: number };
export type ClassificationQueue = { items: { document_id: string; filename: string; page_count: number; created_at: string;
  state: CategoryState; category_id: string | null; category_name: string | null; confidence: number | null }[];
  total: number; limit: number; offset: number };
export type SnippetPart = { text: string; match: boolean };
export type SearchPage = { page_no: number; source: TextSource; revision: number | null; match_count: number;
  snippets: SnippetPart[][] };
export type SearchItem = { document: DocumentRecord; score: number; filename_match: boolean; matched_pages: number;
  pages: SearchPage[] };
export type ClassifierCard = { id: string; method: string; threshold: number; source: string; trained_at: string;
  classes: string[]; examples: Record<string, number>; left_out: Record<string, number> };
export type ClassifierInfo = { active_method: string; model: ClassifierCard | null;
  confirmed_examples: Record<string, number>; min_per_category: number };
export type SearchResult = { query: string; terms: string[]; items: SearchItem[]; total: number; limit: number;
  offset: number; truncated: boolean; mode: "ranked" | "exact"; method?: string };
export type Revision = { id: string; version: number; base_source: TextSource; base_run_id: string | null; note: string;
  author: string; created_at: string; characters: number };
export type RevisionText = Revision & { text: string; document_id: string; page_no: number };
export type PageText = { document_id: string; page_no: number; available: boolean; source: TextSource | null;
  text: string | null; run_id: string | null; version: number; reviewed: boolean; ocr_confidence: number | null;
  review_required: boolean | null; blank: boolean | null; revisions: Revision[] };
export type ReviewItem = { document_id: string; filename: string; page_count: number; page_no: number;
  mean_confidence: number | null; quality_score: number; text_length: number; run_id: string; finished_at: string };
export type ReviewQueue = { items: ReviewItem[]; total: number; reviewed_pages: number; limit: number; offset: number };

// Empty = same origin (Next forwards /api to FastAPI); set NEXT_PUBLIC_API_URL only to call the API directly.
const base = (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/$/, "");
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
export const put = <T,>(path: string, body: unknown) => request<T>("PUT", path, body);

export function upload(file: File, onProgress: (value: number) => void, signal: AbortSignal, folderId?: string): Promise<DocumentRecord> {
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
    const body = new FormData(); body.append("file", file); if (folderId) body.append("folder_id", folderId);
    xhr.send(body);
  });
}
