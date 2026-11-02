"use client";
import Link from "next/link";
import type { EvaluationReport } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useApi } from "@/lib/use-api";
import { date, number, percent } from "@/lib/format";
import { Icon } from "@/components/icons";
import { Failure, Loading } from "@/components/ui";

const bucketNames: Record<string, string> = { low: "ثقة منخفضة (< ٦٠٪)", medium: "متوسطة (٦٠–٨٥٪)", high: "عالية (≥ ٨٥٪)" };

function download(report: EvaluationReport) {
  const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `smartarchive-evaluation-${report.generated_at.slice(0, 10)}.json`;
  link.click();
  URL.revokeObjectURL(link.href);
}

export default function Evaluation() {
  const { can } = useAuth();
  const allowed = can("review.write");
  const resource = useApi<EvaluationReport>(allowed ? "/evaluation" : null);
  if (!allowed) return <section className="panel"><div className="empty-state"><div className="empty-icon"><Icon name="lock" /></div><h3>التقييم متاح للمراجعين وموظفي الأرشيف</h3></div></section>;
  if (resource.loading) return <Loading label="جار حساب المقاييس…" />;
  if (resource.error) return <Failure message={resource.error} retry={resource.reload} />;
  const data = resource.data!, ocr = data.ocr, cls = data.classification;
  const labels = Object.keys(cls.confusion);
  const columns = [...new Set(labels.flatMap(label => Object.keys(cls.confusion[label])))].sort((a, b) => a === "abstain" ? 1 : b === "abstain" ? -1 : a.localeCompare(b));
  const name = (id: string) => id === "abstain" ? "امتنع" : cls.names[id] ?? id;
  return <>
    <div className="page-heading"><div><span className="eyebrow">القياس</span><h1>تقييم النظام على بيانات الأرشيف</h1>
      <p>مقاييس محسوبة من تصحيحات المراجعين وتصنيفاتهم المعتمدة · {date(data.generated_at)}</p></div>
      <div className="heading-actions"><button className="button secondary" onClick={resource.reload}><Icon name="refresh" />إعادة الحساب</button>
        <button className="button primary" onClick={() => download(data)}><Icon name="download" />تنزيل JSON</button></div></div>

    <section className="stats-grid" aria-label="ملخص التقييم">
      <article className="stat-card"><span className="stat-icon"><Icon name="text" /></span><span>معدل أخطاء الحروف CER</span><strong data-testid="micro-cer">{percent(ocr.summary.micro_cer)}</strong><small>على {number(ocr.summary.pages)} صفحة مصحّحة · {number(ocr.summary.chars)} حرفًا</small></article>
      <article className="stat-card"><span className="stat-icon mint"><Icon name="text" /></span><span>معدل أخطاء الكلمات WER</span><strong>{percent(ocr.summary.micro_wer)}</strong><small>{number(ocr.summary.words)} كلمة مرجعية</small></article>
      <article className="stat-card"><span className="stat-icon sand"><Icon name="tag" /></span><span>دقة اقتراح التصنيف</span><strong data-testid="classification-accuracy">{percent(cls.summary.accuracy_when_suggested)}</strong><small>عند الاقتراح · التغطية {percent(cls.summary.coverage)} من {number(cls.summary.labelled)} مستند</small></article>
    </section>

    <section className="panel">
      <div className="section-heading"><div><h2>دقة OCR حسب ثقة المحرك</h2><p>{ocr.note === "Post-editing rate against human-corrected pages (not an independent ground truth)." ? "معدل التحرير بعد التصحيح البشري: يقيس ما غيّره المراجع، وليس مرجعًا مستقلًا؛ والصفحات المراجعة غالبًا منخفضة الثقة." : ocr.note} · سياسة القياس <span dir="ltr">{ocr.policy}</span> (يتجاهل التشكيل والتطويل)</p></div></div>
      {ocr.summary.pages === 0 ? <div className="empty-state"><div className="empty-icon"><Icon name="edit" /></div><h3>لا توجد صفحات مصحّحة بعد</h3><p>صحّح صفحات من <Link className="text-link" href="/review">قائمة المراجعة</Link> لتظهر المقاييس.</p></div> : <>
        <div className="table-scroll"><table><thead><tr><th>فئة الثقة</th><th>الصفحات</th><th>CER</th></tr></thead><tbody>
          {ocr.by_confidence.map(bucket => <tr key={bucket.bucket}><td>{bucketNames[bucket.bucket] ?? bucket.bucket}</td><td>{number(bucket.pages)}</td><td>{percent(bucket.micro_cer)}</td></tr>)}
        </tbody></table></div>
        <details className="steps-detail eval-details"><summary>الصفحات ({number(ocr.pages.length)}){ocr.truncated && " · عُرضت أول ٣٠٠ صفحة"}</summary>
          <div className="table-scroll"><table><thead><tr><th>المستند</th><th>الصفحة</th><th>ثقة OCR</th><th>CER</th><th>WER</th><th>أخطاء / حروف</th></tr></thead><tbody>
            {ocr.pages.map(page => <tr key={`${page.document_id}-${page.page_no}`}><td><Link className="text-link" href={`/documents/${page.document_id}?page=${page.page_no}`} dir="auto">{page.filename}</Link></td>
              <td>{number(page.page_no)}</td><td>{percent(page.ocr_confidence)}</td><td>{percent(page.cer)}</td><td>{percent(page.wer)}</td><td>{number(page.char_errors)} / {number(page.chars)}</td></tr>)}
          </tbody></table></div></details>
      </>}
    </section>

    <section className="panel">
      <div className="section-heading"><div><h2>دقة التصنيف الآلي (<span dir="ltr">{cls.method}</span>)</h2><p>المرجع: التصنيف الذي اعتمده شخص. التنبؤ: الاقتراح الذي رآه عند الاعتماد. المراجع رأى الاقتراح، لذا قد تكون الدقة متفائلة.</p></div>
        <span className="neutral-tag">Macro-F1 {percent(cls.summary.macro_f1)}</span></div>
      {cls.summary.labelled === 0 ? <div className="empty-state"><div className="empty-icon"><Icon name="tag" /></div><h3>لا توجد تصنيفات معتمدة بعد</h3></div> : <>
        <div className="table-scroll"><table><thead><tr><th>الفئة</th><th>عدد المرجع</th><th>اقتُرحت</th><th>الدقة Precision</th><th>الاسترجاع Recall</th><th>F1</th></tr></thead><tbody>
          {cls.per_category.map(item => <tr key={item.category_id}><td>{item.name}</td><td>{number(item.support)}</td><td>{number(item.predicted)}</td><td>{percent(item.precision)}</td><td>{percent(item.recall)}</td><td>{percent(item.f1)}</td></tr>)}
        </tbody></table></div>
        <h3 className="matrix-title">مصفوفة الالتباس (الصفوف: المرجع، الأعمدة: الاقتراح)</h3>
        <div className="table-scroll"><table className="confusion"><thead><tr><th></th>{columns.map(column => <th key={column}>{name(column)}</th>)}</tr></thead><tbody>
          {labels.map(label => <tr key={label}><th>{name(label)}</th>{columns.map(column => { const value = cls.confusion[label][column] ?? 0;
            return <td key={column} className={value ? column === label ? "hit" : "miss" : ""}>{value ? number(value) : "·"}</td>; })}</tr>)}
        </tbody></table></div>
      </>}
    </section>
    <p className="muted small-note">لتقرير التخرج: <span dir="ltr">tools\archive_ops.py evaluate</span> يحفظ نفس المقاييس JSON وCSV للصفحات في <span dir="ltr">results\evaluation</span>.</p>
  </>;
}
