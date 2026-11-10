"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { apiUrl, patch, post, type AuditEvent, type DocumentRecord, type Folder, type OcrLine, type OcrPage, type OcrSummary,
  type PageAnalysis, type Processing } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useApi } from "@/lib/use-api";
import { actors, bytes, date, decimal, matchWords, number, percent, reasons } from "@/lib/format";
import { Icon } from "@/components/icons";
import { Failure, FileSymbol, Loading, StatusBadge } from "@/components/ui";
import { PageReview } from "@/components/page-review";
import { ClassificationPanel } from "@/components/classification-panel";
import { MetadataPanel } from "@/components/metadata-panel";
import { RelationsPanel } from "@/components/relations-panel";

const actions: Record<string, string> = {
  "document.uploaded": "رفع المستند وحفظ الأصل",
  "document.viewed": "عرض بيانات المستند",
  "document.downloaded": "طلب تنزيل الأصل",
  "document.previewed": "طلب معاينة المستند",
  "ocr.queued": "إضافة المستند إلى قائمة المعالجة",
  "ocr.started": "بدء فحص الجودة واستخراج النص",
  "ocr.completed": "اكتمال استخراج النص",
  "ocr.failed": "فشل المعالجة",
  "ocr.requeued": "إعادة المعالجة إلى قائمة الانتظار",
  "page.reviewed": "تصحيح نص صفحة ومراجعتها",
  "classification.confirmed": "اعتماد تصنيف المستند",
  "classification.changed": "إعادة تصنيف المستند",
  "document.filed": "نقل المستند إلى مجلد",
  "metadata.edited": "تصحيح بيانات وصفية",
  "relation.confirmed": "تأكيد علاقة تكرار أو نسخة",
  "relation.rejected": "رفض علاقة تكرار أو نسخة",
};
const routes = { fast: "سريع (صفحة نظيفة)", layout: "واعٍ بالتخطيط", advanced: "متقدم (صفحة صعبة)" };
const layouts = { simple: "عمود واحد", multi_column: "متعدد الأعمدة", tabular: "يحتوي جدولًا" };
const dpiSources = { metadata: "من بيانات الملف", rendered: "دقة التحويل من PDF", estimated_a4: "تقدير بافتراض A4" };
const tone = (value: number | null) => value === null ? "unknown" : value >= 0.85 ? "good" : value >= 0.6 ? "fair" : "low";

export default function Detail({ id, initialPage = 1, query = "" }: { id: string; initialPage?: number; query?: string }) {
  const { can } = useAuth();
  const resource = useApi<DocumentRecord>(`/documents/${id}`);
  const [active, setActive] = useState(false);
  const processing = useApi<Processing>(`/documents/${id}/status`, active ? 2000 : false);
  const summary = useApi<OcrSummary>(`/documents/${id}/ocr`, active ? 2000 : false);
  const audit = useApi<{ items: AuditEvent[] }>(`/documents/${id}/audit`);
  const [page, setPage] = useState(initialPage);
  const [previewError, setPreviewError] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(true);
  const [showBoxes, setShowBoxes] = useState(true);
  const [focused, setFocused] = useState<number>();
  const [actionError, setActionError] = useState(""), [starting, setStarting] = useState(false);
  const [textVersion, setTextVersion] = useState(0);  // a page correction can change the suggested category
  const folders = useApi<{ items: Folder[] }>(can("documents.upload") ? "/folders" : null);
  const [moving, setMoving] = useState(false), [moveError, setMoveError] = useState("");
  async function move(folderId: string) {
    setMoving(true); setMoveError("");
    try { await patch(`/documents/${id}/folder`, { folder_id: folderId || null }); resource.reload(); audit.reload(); }
    catch (failure) { setMoveError(failure instanceof Error ? failure.message : "تعذر نقل المستند."); }
    finally { setMoving(false); }
  }

  const status = processing.data?.status ?? resource.data?.status;
  // Status and run summary poll separately and both stop when processing ends, so the summary is fetched once
  // more at that moment: its last poll may predate the run becoming ready (the page then stayed on "processing").
  const reloadSummary = summary.reload;
  const wasRunning = useRef(false);
  useEffect(() => {
    const running = status === "queued" || status === "processing";
    if (wasRunning.current && !running) reloadSummary();
    wasRunning.current = running;
    setActive(running);
  }, [status, reloadSummary]);
  const run = summary.data?.run;
  const readyRun = run?.status === "ready" ? run : undefined;
  const ocrPage = useApi<OcrPage>(readyRun ? `/documents/${id}/ocr/pages/${page}?run_id=${readyRun.id}` : null);
  const analysis: PageAnalysis | undefined = summary.data?.pages.find(item => item.page_no === page);

  useEffect(() => {
    // Search results link to a specific page with ?page=n; out-of-range values are clamped below.
    const requested = Number(new URLSearchParams(window.location.search).get("page"));
    setPage(Number.isInteger(requested) && requested >= 1 ? requested : 1);
    setPreviewError(false); setPreviewLoading(true);
  }, [id]);
  const pageCount = resource.data?.page_count;
  useEffect(() => { if (pageCount && page > pageCount) setPage(pageCount); }, [page, pageCount]);
  useEffect(() => { setFocused(undefined); }, [page, readyRun?.id]);

  function changePage(value: number) {
    setPage(value); setPreviewError(false); setPreviewLoading(true);
  }
  async function startOcr() {
    setActionError(""); setStarting(true);
    try { await post(`/documents/${id}/ocr`); setActive(true); processing.reload(); summary.reload(); audit.reload(); }
    catch (failure) { setActionError(failure instanceof Error ? failure.message : "تعذر بدء المعالجة."); }
    finally { setStarting(false); }
  }

  if (resource.loading) return <Loading label="جار تحميل المستند…" />;
  if (resource.error) return <>
    <Link className="text-link" href="/documents">العودة إلى المستندات<Icon name="arrow" /></Link>
    <Failure message={resource.error} retry={resource.reload} />
  </>;
  const doc = resource.data!;
  const lines = ocrPage.data?.lines ?? [];
  const matched = new Set(query ? lines.filter(line => matchWords(line.text, query)).map(line => line.line_no) : []);

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
          <div className="preview-tools">
            {matched.size > 0 && <span className="evidence-tag" role="status">مظلّل: {number(matched.size)} سطر يحوي «<span dir="auto">{query}</span>»</span>}
            {lines.length > 0 && <label className="toggle"><input type="checkbox" checked={showBoxes} onChange={e => setShowBoxes(e.target.checked)} />إظهار مواقع النص</label>}
            <span className="neutral-tag">الصفحة {number(page)} من {number(doc.page_count)}</span>
          </div>
        </div>
        <div className="preview-surface">
          {previewError ? <Failure message="تعذرت المعاينة. يمكنك تنزيل الأصل دون تعديل." /> : <>
            {previewLoading && <Loading label="جار تجهيز المعاينة…" />}
            <div className="page-figure" style={previewLoading ? { display: "none" } : undefined}>
              <img key={`${id}-${page}`} alt={`معاينة ${doc.filename}`}
                src={apiUrl(`/documents/${id}/preview?page=${page}`)}
                onLoad={() => setPreviewLoading(false)}
                onError={() => { setPreviewError(true); setPreviewLoading(false); }} />
              {showBoxes && lines.map(line => <span key={line.line_no} aria-hidden="true"
                className={`ocr-box tone-${tone(line.confidence)} ${focused === line.line_no ? "focused" : ""} ${matched.has(line.line_no) ? "evidence" : ""}`}
                style={{ left: `${line.box[0] * 100}%`, top: `${line.box[1] * 100}%`,
                  width: `${(line.box[2] - line.box[0]) * 100}%`, height: `${(line.box[3] - line.box[1]) * 100}%` }}
                onMouseEnter={() => setFocused(line.line_no)} onMouseLeave={() => setFocused(undefined)} />)}
            </div>
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
        <section className="panel processing-panel" aria-live="polite">
          <div className="section-heading compact-heading">
            <h2>المعالجة والاستخراج</h2>
            {can("ocr.run") && summary.data?.engine.configured && !active &&
              <button className="button secondary compact" disabled={starting} onClick={startOcr}>
                <Icon name={run ? "refresh" : "play"} />{run ? "إعادة المعالجة" : "بدء المعالجة"}</button>}
          </div>
          {processing.loading || summary.loading ? <Loading /> : processing.error ?
            <Failure message={processing.error} retry={processing.reload} /> : <>
              <div className="processing-line"><StatusBadge status={processing.data!.status} />
                <span>{reasons[processing.data!.reason] || processing.data!.reason}</span></div>
              {actionError && <Failure message={actionError} />}
              {!summary.data?.engine.configured && <p className="muted">محرك OCR غير مهيأ على الخادم، لذلك لا توجد نتائج استخراج. {summary.data?.engine.error && <small className="block" dir="ltr">{summary.data.engine.error}</small>}</p>}
              {run && (run.status === "queued" || run.status === "processing") && <div className="run-progress">
                <span>{run.status === "queued" ? "في قائمة الانتظار…" : `جارٍ معالجة الصفحة ${number(Math.min(run.pages_done + 1, run.pages_total))} من ${number(run.pages_total)}`}</span>
                <div className="progress-track"><span style={{ width: `${(run.pages_done / Math.max(run.pages_total, 1)) * 100}%` }} /></div>
              </div>}
              {run?.status === "failed" && <Failure message={`فشلت المعالجة: ${run.error || "خطأ غير معروف"}`} />}
              {readyRun && <dl className="run-facts">
                <div><dt>متوسط ثقة OCR</dt><dd><span className={`confidence tone-${tone(readyRun.mean_confidence)}`}>{percent(readyRun.mean_confidence)}</span></dd></div>
                <div><dt>المحرك</dt><dd dir="ltr">{readyRun.engine} {readyRun.engine_version} · {readyRun.languages}</dd></div>
                <div><dt>نُفّذت بطلب</dt><dd dir="auto">{actors(readyRun.created_by)} · {readyRun.finished_at ? date(readyRun.finished_at) : "—"}</dd></div>
                {readyRun.review_required && (processing.data!.pending_review_pages > 0
                  ? <div className="review-flag"><Icon name="alert" />{number(processing.data!.pending_review_pages)} صفحة بثقة منخفضة أو بلا نص بانتظار المراجعة البشرية.</div>
                  : <div className="saved-note"><Icon name="check" />روجعت جميع الصفحات المشكوك فيها.</div>)}
              </dl>}
            </>}
        </section>

        <ClassificationPanel key={`${id}-${readyRun?.id ?? "none"}-${textVersion}`} documentId={id} onChanged={audit.reload} />

        <MetadataPanel key={`meta-${id}-${readyRun?.id ?? "none"}-${textVersion}`} documentId={id} onChanged={() => { audit.reload(); setTextVersion(value => value + 1); }} />

        <RelationsPanel key={`rel-${id}-${readyRun?.id ?? "none"}-${textVersion}`} documentId={id} />

        {analysis && <QualityPanel analysis={analysis} />}

        <section className="panel metadata-panel">
          <h2>بيانات المستند</h2>
          <dl>
            <div><dt>الحالة</dt><dd><StatusBadge status={status ?? doc.status} /></dd></div>
            <div><dt>المجلد</dt><dd>{can("documents.upload") && folders.data ? <select aria-label="مجلد المستند" className="inline-select" value={doc.folder_id ?? ""} disabled={moving} onChange={e => move(e.target.value)}>
              <option value="">بدون مجلد</option>{folders.data.items.map(item => <option key={item.id} value={item.id}>{item.path}</option>)}</select>
              : <span dir="auto">{doc.folder_path ?? "—"}</span>}{moveError && <small className="error-text">{moveError}</small>}</dd></div>
            <div><dt>نوع الملف</dt><dd dir="ltr">{doc.mime_type}</dd></div>
            <div><dt>حجم الأصل</dt><dd>{bytes(doc.size_bytes)}</dd></div>
            <div><dt>عدد الصفحات</dt><dd>{number(doc.page_count)}</dd></div>
            <div><dt>آخر تحديث للحالة</dt><dd>{date(processing.data?.updated_at ?? doc.updated_at)}</dd></div>
          </dl>
          <div className="hash-block">
            <span><Icon name="shield" />بصمة الملف · SHA-256</span>
            <code dir="ltr">{doc.sha256}</code>
            <small>تُفحص سلامة الأصل عند المعاينة والتنزيل.</small>
          </div>
        </section>
      </div>
    </div>

    {readyRun && <section className="panel text-panel">
      <div className="section-heading">
        <div><h2>النص المستخرج · الصفحة {number(page)}</h2>
          <p>نص آلي غير مُراجَع، مرتبط بموقعه على الصفحة. مرّر على سطر لإظهار موقعه.</p></div>
        {analysis && <span className={`confidence tone-${tone(analysis.mean_confidence)}`}>ثقة الصفحة {percent(analysis.mean_confidence)}</span>}
      </div>
      {ocrPage.loading ? <Loading /> : ocrPage.error ? <Failure message={ocrPage.error} retry={ocrPage.reload} /> :
        lines.length === 0 ? <p className="muted">{analysis?.blank ? "صُنّفت هذه الصفحة فارغة ولم يُشغَّل عليها OCR." : "لم يُستخرج نص من هذه الصفحة."}</p> :
          <ol className="ocr-lines">{lines.map((line: OcrLine) => <li key={line.line_no}>
            <button type="button" className={focused === line.line_no ? "focused" : ""}
              onMouseEnter={() => setFocused(line.line_no)} onMouseLeave={() => setFocused(undefined)}
              onFocus={() => setFocused(line.line_no)} onBlur={() => setFocused(undefined)}>
              <span className="line-text" dir="auto">{line.text}</span>
              <span className={`confidence tone-${tone(line.confidence)}`}>{percent(line.confidence)}</span>
            </button></li>)}</ol>}
    </section>}

    {readyRun && <PageReview documentId={id} page={page} onSaved={() => { processing.reload(); audit.reload(); setTextVersion(value => value + 1); }} />}

    {summary.data && summary.data.runs.length > 0 && <section className="panel runs-panel">
      <div className="section-heading"><div><h2>نسخ المعالجة</h2><p>كل تشغيل يُحفظ كنسخة مستقلة ولا يستبدل ما قبله.</p></div></div>
      <div className="table-scroll"><table><thead><tr><th>التاريخ</th><th>الحالة</th><th>المحرك</th><th>الثقة</th><th>بطلب من</th></tr></thead><tbody>
        {summary.data.runs.map(item => <tr key={item.id}><td className="nowrap">{date(item.created_at)}</td>
          <td>{({ queued: "في الانتظار", processing: "قيد التنفيذ", ready: "مكتملة", failed: "فشلت" })[item.status]}</td>
          <td dir="ltr">{item.engine} {item.engine_version}</td><td>{percent(item.mean_confidence)}</td>
          <td dir="auto">{actors(item.created_by)}</td></tr>)}
      </tbody></table></div>
    </section>}

    <section className="panel audit-panel">
      <div className="section-heading">
        <div><h2>سجل الأحداث</h2><p>سجل متتابع لأحداث المستند المحفوظة</p></div>
        <button className="button secondary compact" onClick={audit.reload}>
          <Icon name="refresh" />تحديث السجل
        </button>
      </div>
      {audit.loading ? <Loading /> : audit.error ? <Failure message={audit.error} retry={audit.reload} /> :
        <ol className="audit-list">{audit.data?.items.map(event => <li key={event.sequence}>
          <span className="audit-marker"><Icon name={event.action === "document.uploaded" ? "upload" : event.action.startsWith("ocr.") ? "scan" : event.action === "page.reviewed" ? "edit" : event.action.startsWith("classification.") ? "tag" : "clock"} /></span>
          <div><strong>{actions[event.action] || event.action}</strong>
            <small dir="auto">{actors(event.actor)}</small></div>
          <time dateTime={event.timestamp}>{date(event.timestamp)}</time>
        </li>)}</ol>}
    </section>
  </>;
}

function QualityPanel({ analysis }: { analysis: PageAnalysis }) {
  const m = analysis.metrics;
  const terms: [string, number, boolean][] = [
    ["الوضوح B", m.sharpness, true], ["التباين C", m.contrast, true], ["الدقة R", m.resolution, true],
    ["سلامة الميل S", m.skew, true], ["بساطة التخطيط L", m.layout_simplicity, true], ["خلو الضوضاء", m.noise, false],
  ];
  return <section className="panel quality-panel">
    <div className="section-heading compact-heading"><h2>جودة الصفحة {number(analysis.page_no)}</h2>
      <span className={`quality-score tone-${tone(analysis.quality_score)}`}>Q = {decimal(analysis.quality_score)}</span></div>
    {analysis.blank ? <p className="muted">صفحة فارغة: لا يوجد حبر كافٍ لاستخراج نص.</p> : <>
      <ul className="metric-bars">{terms.map(([label, value, inScore]) => <li key={label}>
        <span>{label}{!inScore && <small> (لا تدخل في Q)</small>}</span>
        <div className="bar"><span style={{ width: `${value * 100}%` }} className={`tone-${tone(value)}`} /></div>
        <b>{decimal(value)}</b></li>)}</ul>
      <dl className="quality-facts">
        <div><dt>المسار المقترح</dt><dd>{routes[analysis.suggested_route]}</dd></div>
        <div><dt>التخطيط</dt><dd>{layouts[m.layout]}{m.columns > 1 ? ` · ${number(m.columns)} أعمدة` : ""}</dd></div>
        <div><dt>زاوية الميل</dt><dd dir="ltr">{m.skew_angle.toFixed(1)}°</dd></div>
        <div><dt>الدقة</dt><dd>{analysis.dpi ? `${number(Math.round(analysis.dpi))} DPI` : "—"} · {dpiSources[analysis.dpi_source]}</dd></div>
      </dl>
      <details className="steps-detail"><summary>خطوات المعالجة المسبقة</summary><ul>
        {analysis.preprocessing.map((step, index) => <li key={index} dir="ltr">{JSON.stringify(step)}</li>)}</ul></details>
      <p className="muted small-note">جميع الصفحات تُستخرج حاليًا بمسار Tesseract الأساسي؛ تفعيل التوجيه بين المسارات الثلاثة في المرحلة التالية.</p>
    </>}
  </section>;
}
