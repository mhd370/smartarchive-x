export type Status = "stored" | "queued" | "processing" | "ready" | "failed";
export type DocumentRecord = {
  id: string; filename: string; size_bytes: number; mime_type: string; sha256: string;
  page_count: number; status: Status; status_reason: string; created_at: string; updated_at: string;
};
export type DocumentList = { items: DocumentRecord[]; total: number; limit: number; offset: number };
export type Statistics = { total_documents: number; total_bytes: number; by_status: Record<Status, number> };
export type Health = { status: string; ocr_configured: boolean; max_upload_bytes: number; supported_extensions: string[] };
export type Processing = { document_id: string; status: Status; reason: string; ocr_configured: boolean;
  extracted_text: string | null; ocr_confidence: number | null; classification: string | null };
export type AuditEvent = { sequence: number; action: string; actor: string; timestamp: string };

const base = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
export const apiUrl = (path: string) => `${base}/api${path}`;

function message(body: unknown, fallback: string) {
  if (body && typeof body === "object" && "detail" in body && typeof body.detail === "string") return body.detail;
  return fallback;
}
export async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  let response: Response;
  try { response = await fetch(apiUrl(path), { signal, cache: "no-store" }); }
  catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new Error("تعذر الاتصال بالخدمة. تأكد من تشغيل الخادم ثم أعد المحاولة.");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(message(body, response.status === 404 ? "المستند غير موجود." : "تعذر إكمال الطلب. حاول مرة أخرى."));
  }
  return response.json() as Promise<T>;
}

export function upload(file: File, onProgress: (value: number) => void, signal: AbortSignal): Promise<DocumentRecord> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("POST", apiUrl("/documents"));
    request.responseType = "json";
    request.timeout = 120_000;
    request.upload.onprogress = event => { if (event.lengthComputable) onProgress(Math.round(event.loaded * 100 / event.total)); };
    request.onload = () => {
      if (request.status === 201 && request.response?.id) resolve(request.response as DocumentRecord);
      else reject(new Error(message(request.response, "لم يكتمل حفظ المستند. تحقق من الملف وحاول مجددًا.")));
    };
    request.onerror = () => reject(new Error("انقطع الاتصال. تحقق من قائمة المستندات قبل إعادة الرفع."));
    request.ontimeout = () => reject(new Error("انتهت مهلة الطلب. تحقق من قائمة المستندات قبل إعادة المحاولة."));
    request.onabort = () => reject(new Error("أُلغي الطلب. تحقق من قائمة المستندات إذا كان الإرسال قد اكتمل."));
    const cancel = () => request.abort();
    signal.addEventListener("abort", cancel, { once: true });
    request.onloadend = () => signal.removeEventListener("abort", cancel);
    const body = new FormData(); body.append("file", file);
    request.send(body);
  });
}
