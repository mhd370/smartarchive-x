"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { apiUrl, type AuditEvent, type DocumentRecord, type Processing } from "@/lib/api";
import { useApi } from "@/lib/use-api";
import { bytes, date, number } from "@/lib/format";
import { Icon } from "@/components/icons";
import { Failure, FileSymbol, Loading, StatusBadge } from "@/components/ui";

const actions: Record<string, string> = {
  "document.uploaded": "رفع المستند وحفظ الأصل",
  "document.viewed": "عرض بيانات المستند",
  "document.downloaded": "طلب تنزيل الأصل",
  "document.previewed": "طلب معاينة المستند",
};

export default function Detail({ id }: { id: string }) {
  const resource = useApi<DocumentRecord>(`/documents/${id}`);
  const processing = useApi<Processing>(`/documents/${id}/status`);
  const audit = useApi<{ items: AuditEvent[] }>(`/documents/${id}/audit`);
  const [page, setPage] = useState(1);
  const [previewError, setPreviewError] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(true);

  useEffect(() => {
    setPage(1); setPreviewError(false); setPreviewLoading(true);
  }, [id]);

  function changePage(value: number) {
    setPage(value); setPreviewError(false); setPreviewLoading(true);
  }

  if (resource.loading) return <Loading label="جار تحميل المستند…" />;
  if (resource.error) return <>
    <Link className="text-link" href="/documents">العودة إلى المستندات<Icon name="arrow" /></Link>
    <Failure message={resource.error} retry={resource.reload} />
  </>;
  const doc = resource.data!;

  return <>
    <Link href="/documents" className="text-link back-link">المستندات<Icon name="arrow" /></Link>
    <div className="page-heading detail-heading">
      <div className="detail-name">
        <FileSymbol mime={doc.mime_type} />
        <div><h1 dir="auto">{doc.filename}</h1><p>أضيف في {date(doc.created_at)}</p></div>
      </div>
      <a className="button primary" href={apiUrl(`/documents/${id}/download`)}>
        <Icon name="download" />تنزيل الأصل
      </a>
    </div>

    <div className="detail-layout">
      <section className="panel preview-panel">
        <div className="section-heading">
          <div><h2>معاينة المستند</h2><p>معاينة مرئية من الأصل · الملف الأصلي متاح للتنزيل دون تعديل</p></div>
          <span className="neutral-tag">الصفحة {number(page)} من {number(doc.page_count)}</span>
        </div>
        <div className="preview-surface">
          {previewError ? <Failure message="تعذرت المعاينة. يمكنك تنزيل الأصل دون تعديل." /> : <>
            {previewLoading && <Loading label="جار تجهيز المعاينة…" />}
            <img key={`${id}-${page}`} alt={`معاينة ${doc.filename}`}
              src={apiUrl(`/documents/${id}/preview?page=${page}`)}
              style={previewLoading ? { display: "none" } : undefined}
              onLoad={() => setPreviewLoading(false)}
              onError={() => { setPreviewError(true); setPreviewLoading(false); }} />
          </>}
        </div>
        {doc.page_count > 1 && <div className="pagination">
          <span>الصفحة {number(page)} من {number(doc.page_count)}</span>
          <div>
            <button className="button secondary compact" disabled={page === 1}
              onClick={() => changePage(page - 1)}>الصفحة السابقة</button>
            <button className="button secondary compact" disabled={page === doc.page_count}
              onClick={() => changePage(page + 1)}>الصفحة التالية</button>
          </div>
        </div>}
      </section>

      <div className="detail-aside">
        <section className="panel metadata-panel">
          <h2>بيانات المستند</h2>
          <dl>
            <div><dt>الحالة</dt><dd><StatusBadge status={doc.status} /></dd></div>
            <div><dt>نوع الملف</dt><dd dir="ltr">{doc.mime_type}</dd></div>
            <div><dt>حجم الأصل</dt><dd>{bytes(doc.size_bytes)}</dd></div>
            <div><dt>عدد الصفحات</dt><dd>{number(doc.page_count)}</dd></div>
            <div><dt>آخر تحديث للحالة</dt><dd>{date(doc.updated_at)}</dd></div>
          </dl>
          <div className="hash-block">
            <span><Icon name="shield" />بصمة الملف · SHA-256</span>
            <code dir="ltr">{doc.sha256}</code>
            <small>تُفحص سلامة الأصل عند المعاينة والتنزيل.</small>
          </div>
        </section>
        <section className="panel processing-panel">
          <h2>المعالجة والاستخراج</h2>
          {processing.loading ? <Loading /> : processing.error ?
            <Failure message={processing.error} retry={processing.reload} /> : <>
              <div className="processing-line"><Icon name="clock" />
                <strong>{processing.data?.ocr_configured ? "حالة المعالجة المسجلة" : "المعالجة الآلية غير مفعلة"}</strong>
              </div>
              <p>حُفظ الأصل بنجاح. لا تتوفر نتائج استخراج أو تصنيف أو درجة ثقة لهذا المستند.</p>
            </>}
        </section>
      </div>
    </div>

    <section className="panel audit-panel">
      <div className="section-heading">
        <div><h2>سجل الأحداث</h2><p>سجل متتابع لأحداث المستند المحفوظة</p></div>
        <button className="button secondary compact" onClick={audit.reload}>
          <Icon name="refresh" />تحديث السجل
        </button>
      </div>
      {audit.loading ? <Loading /> : audit.error ? <Failure message={audit.error} retry={audit.reload} /> :
        <ol className="audit-list">{audit.data?.items.map(event => <li key={event.sequence}>
          <span className="audit-marker"><Icon name={event.action === "document.uploaded" ? "upload" : "clock"} /></span>
          <div><strong>{actions[event.action] || event.action}</strong>
            <small>{event.actor === "local" ? "جلسة محلية" : event.actor}</small></div>
          <time dateTime={event.timestamp}>{date(event.timestamp)}</time>
        </li>)}</ol>}
    </section>
  </>;
}
