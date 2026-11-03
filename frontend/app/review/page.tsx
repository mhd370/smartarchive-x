"use client";
import { useState } from "react";
import Link from "next/link";
import type { ClassificationQueue, ReclassificationQueue, ReviewQueue } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useApi } from "@/lib/use-api";
import { date, decimal, number, percent } from "@/lib/format";
import { Icon } from "@/components/icons";
import { CategoryBadge, Failure, Loading } from "@/components/ui";

const PAGE_SIZE = 25;
const tone = (value: number | null) => value === null ? "unknown" : value >= 0.85 ? "good" : value >= 0.6 ? "fair" : "low";

export default function Review() {
  const { can } = useAuth();
  const [offset, setOffset] = useState(0);
  const allowed = can("review.write");
  const queue = useApi<ReviewQueue>(allowed ? `/review/queue?limit=${PAGE_SIZE}&offset=${offset}` : null);
  const [classOffset, setClassOffset] = useState(0);
  const classes = useApi<ClassificationQueue>(allowed ? `/classification/queue?limit=${PAGE_SIZE}&offset=${classOffset}` : null);
  const reclass = useApi<ReclassificationQueue>(allowed ? `/classification/reclassification?limit=${PAGE_SIZE}` : null);
  if (!allowed) return <section className="panel"><div className="empty-state"><div className="empty-icon"><Icon name="lock" /></div>
    <h3>المراجعة متاحة للمراجعين وموظفي الأرشيف</h3><p>اطلب من مدير النظام صلاحية مراجع إذا كان عملك يتطلب تصحيح النصوص.</p></div></section>;
  return <>
    <div className="page-heading"><div><span className="eyebrow">ضبط الجودة</span><h1>صفحات بانتظار المراجعة</h1>
      <p>صفحات ثقة قراءتها الآلية منخفضة أو لم يُستخرج منها نص. الأقل ثقة أولًا.</p></div>
      <button className="button secondary" onClick={() => { queue.reload(); classes.reload(); reclass.reload(); }}><Icon name="refresh" />تحديث القائمة</button></div>
    <section className="panel">
      {queue.loading ? <Loading /> : queue.error ? <Failure message={queue.error} retry={queue.reload} /> : queue.data && <>
        <div className="search-summary">{number(queue.data.total)} صفحة بانتظار المراجعة · {number(queue.data.reviewed_pages)} صفحة رُوجعت حتى الآن</div>
        {queue.data.total === 0 ? <div className="empty-state"><div className="empty-icon"><Icon name="check" /></div><h3>لا توجد صفحات بانتظار المراجعة</h3>
          <p>كل الصفحات المعالجة إمّا عالية الثقة أو صُحّحت بالفعل.</p></div>
          : <div className="table-scroll"><table><thead><tr><th>المستند</th><th>الصفحة</th><th>ثقة OCR</th><th>جودة الصفحة Q</th><th>طول النص</th><th>اكتملت المعالجة</th><th><span className="sr-only">مراجعة</span></th></tr></thead>
            <tbody>{queue.data.items.map(item => <tr key={`${item.document_id}-${item.page_no}`}>
              <td><Link className="document-name" href={`/documents/${item.document_id}?page=${item.page_no}`}><span><strong dir="auto">{item.filename}</strong><small>{number(item.page_count)} صفحة</small></span></Link></td>
              <td>{number(item.page_no)}</td>
              <td><span className={`confidence tone-${tone(item.mean_confidence)}`}>{percent(item.mean_confidence)}</span></td>
              <td>{decimal(item.quality_score)}</td>
              <td>{item.text_length ? `${number(item.text_length)} حرفًا` : "بلا نص"}</td>
              <td className="muted nowrap">{date(item.finished_at)}</td>
              <td><Link className="button secondary compact" href={`/documents/${item.document_id}?page=${item.page_no}`}><Icon name="edit" />مراجعة</Link></td>
            </tr>)}</tbody></table></div>}
        {queue.data.total > PAGE_SIZE && <div className="pagination"><span>عرض {number(offset + 1)}–{number(offset + queue.data.items.length)} من {number(queue.data.total)}</span>
          <div><button className="button secondary compact" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>السابق</button>
            <button className="button secondary compact" disabled={offset + queue.data.items.length >= queue.data.total} onClick={() => setOffset(offset + PAGE_SIZE)}>التالي</button></div></div>}
      </>}
    </section>
    <section className="panel" aria-labelledby="classification-queue">
      <div className="section-heading"><div><h2 id="classification-queue">تصنيفات بانتظار الاعتماد</h2>
        <p>مستندات لها اقتراح آلي لم يعتمده أحد بعد، أو لم يستطع النظام تصنيفها. الأعلى ثقة أولًا.</p></div></div>
      {classes.loading ? <Loading /> : classes.error ? <Failure message={classes.error} retry={classes.reload} /> : classes.data && <>
        {classes.data.total === 0 ? <div className="empty-state"><div className="empty-icon"><Icon name="check" /></div><h3>كل التصنيفات معتمدة</h3></div>
          : <div className="table-scroll"><table><thead><tr><th>المستند</th><th>الاقتراح</th><th>الثقة</th><th>تاريخ الإضافة</th><th><span className="sr-only">اعتماد</span></th></tr></thead>
            <tbody>{classes.data.items.map(item => <tr key={item.document_id}>
              <td><Link className="document-name" href={`/documents/${item.document_id}`}><span><strong dir="auto">{item.filename}</strong><small>{number(item.page_count)} صفحة</small></span></Link></td>
              <td><CategoryBadge name={item.category_name} state={item.state} /></td>
              <td>{percent(item.confidence)}</td>
              <td className="muted nowrap">{date(item.created_at)}</td>
              <td><Link className="button secondary compact" href={`/documents/${item.document_id}`}><Icon name="tag" />مراجعة التصنيف</Link></td>
            </tr>)}</tbody></table></div>}
        {classes.data.total > PAGE_SIZE && <div className="pagination"><span>عرض {number(classOffset + 1)}–{number(classOffset + classes.data.items.length)} من {number(classes.data.total)}</span>
          <div><button className="button secondary compact" disabled={classOffset === 0} onClick={() => setClassOffset(Math.max(0, classOffset - PAGE_SIZE))}>السابق</button>
            <button className="button secondary compact" disabled={classOffset + classes.data.items.length >= classes.data.total} onClick={() => setClassOffset(classOffset + PAGE_SIZE)}>التالي</button></div></div>}
      </>}
    </section>
    <section className="panel" aria-labelledby="reclassification-queue">
      <div className="section-heading"><div><h2 id="reclassification-queue">اقتراحات إعادة التصنيف</h2>
        <p>مستندات معتمدة ظهرت لها أدلة جديدة قوية على فئة أخرى. لا يتغيّر أي تصنيف معتمد إلا بقرار مراجع. الأقوى دليلًا أولًا.</p></div></div>
      {reclass.loading ? <Loading /> : reclass.error ? <Failure message={reclass.error} retry={reclass.reload} /> : reclass.data && <>
        {reclass.data.total === 0 ? <div className="empty-state"><div className="empty-icon"><Icon name="check" /></div><h3>لا توجد اقتراحات إعادة تصنيف</h3></div>
          : <div className="table-scroll"><table><thead><tr><th>المستند</th><th>المعتمد حاليًا</th><th>المقترح</th><th>الفرق</th><th><span className="sr-only">مراجعة</span></th></tr></thead>
            <tbody>{reclass.data.items.map(item => <tr key={item.document_id}>
              <td><Link className="document-name" href={`/documents/${item.document_id}`}><span><strong dir="auto">{item.filename}</strong></span></Link></td>
              <td>{item.from_category_name ?? item.from_category_id}</td>
              <td><b>{item.to_category_name ?? item.to_category_id}</b> · {percent(item.share)}</td>
              <td>{percent(item.delta)}</td>
              <td><Link className="button secondary compact" href={`/documents/${item.document_id}`}><Icon name="tag" />مراجعة</Link></td>
            </tr>)}</tbody></table></div>}
      </>}
    </section>
  </>;
}
