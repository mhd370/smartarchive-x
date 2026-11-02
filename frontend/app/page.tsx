"use client";
import Link from "next/link";
import { useApi } from "@/lib/use-api";
import type { Statistics, DocumentList, Status } from "@/lib/api";
import { bytes, number, statuses } from "@/lib/format";
import { Icon } from "@/components/icons";
import { DocumentTable, Empty, Failure, Loading } from "@/components/ui";
import { Can } from "@/components/can";
import { useAuth } from "@/lib/auth";

export default function Dashboard() {
  const { can } = useAuth();
  const stats = useApi<Statistics>("/statistics"), recent = useApi<DocumentList>("/documents?limit=5");
  return <>
    <div className="page-heading"><div><span className="eyebrow">مساحة عمل المستندات</span><h1>نظرة عامة على أرشيفك</h1><p>تابع مستنداتك وحالتها ومراجعة نصوصها من مكان واحد.</p></div><button className="button secondary" onClick={() => { stats.reload(); recent.reload(); }}><Icon name="refresh" />تحديث البيانات</button></div>
    <section className="welcome-panel"><div><span className="section-kicker"><span />حفظ موثوق للمستندات</span><h2>كل مستند له مكان.<br />وكل أصل يبقى محفوظًا.</h2><p>ارفع مستنداتك العربية، ابحث داخل نصوصها، وارجع إلى الأصل متى احتجت إليه.</p><Can permission="documents.upload"><Link href="/upload" className="button primary">إضافة مستند<Icon name="arrow" /></Link></Can></div><div className="archive-illustration" aria-hidden="true"><span className="orbit orbit-one" /><span className="orbit orbit-two" /><div className="illustrated-folder"><Icon name="archive" /><span /><span /><span /></div><div className="illustrated-check"><Icon name="check" /></div></div></section>
    {stats.loading ? <Loading label="جار تحميل إحصاءات الأرشيف…" /> : stats.error ? <Failure message={stats.error} retry={stats.reload} /> : stats.data && <>
      <section className="stats-grid" aria-label="إحصاءات الأرشيف"><article className="stat-card"><span className="stat-icon"><Icon name="file" /></span><span>إجمالي المستندات</span><strong data-testid="document-count">{number(stats.data.total_documents)}</strong><small>جميع المستندات المسجلة</small></article><article className="stat-card"><span className="stat-icon mint"><Icon name="review" /></span><span>صفحات بانتظار المراجعة</span><strong data-testid="pending-review">{number(stats.data.pages_pending_review)}</strong><small>{stats.data.pages_reviewed ? `${number(stats.data.pages_reviewed)} صفحة رُوجعت` : "صفحات ثقتها منخفضة"}{can("review.write") && stats.data.pages_pending_review > 0 && <> · <Link href="/review" className="text-link">ابدأ المراجعة</Link></>}</small></article><article className="stat-card"><span className="stat-icon sand"><Icon name="archive" /></span><span>حجم الأرشيف</span><strong className="size-value">{bytes(stats.data.total_bytes)}</strong><small>الحجم الفعلي للملفات الأصلية</small></article></section>
      <section className="panel status-panel"><div className="section-heading"><div><h2>حالة المستندات</h2><p>الحالات المسجلة فعليًا في قاعدة البيانات</p></div><Link href="/search" className="text-link">البحث في النصوص<Icon name="search" /></Link></div><div className="status-breakdown">{(Object.keys(statuses) as Status[]).map(status => <div key={status}><span className={`status-dot dot-${status}`} /><span>{statuses[status]}</span><strong>{number(stats.data!.by_status[status])}</strong></div>)}</div></section>
    </>}
    {stats.data && stats.data.categories.length > 0 && <section className="panel">
      <div className="section-heading"><div><h2>توزيع التصنيفات</h2><p>معتمد بلون كامل، ومقترح لم يُعتمد بعد بلون فاتح.</p></div>
        <Link href="/categories" className="text-link">الفئات<Icon name="arrow" /></Link></div>
      <div className="category-bars">{(() => {
        const max = Math.max(1, ...stats.data!.categories.map(item => item.confirmed + item.suggested));
        return stats.data!.categories.map(item => <Link key={item.id} href={`/documents?category=${item.id}`} className="category-bar">
          <span>{item.name}</span>
          <span className="bar"><span className="confirmed-part" style={{ width: `${(item.confirmed / max) * 100}%` }} /><span className="suggested-part" style={{ width: `${(item.suggested / max) * 100}%` }} /></span>
          <b>{number(item.confirmed)}{item.suggested > 0 && <small> +{number(item.suggested)}</small>}</b>
        </Link>);
      })()}</div>
      <p className="muted small-note category-foot">{number(stats.data.classification.uncertain + stats.data.classification.none)} مستند غير مصنّف · {number(stats.data.classification.suggested)} بانتظار الاعتماد</p>
    </section>}
    <section className="panel"><div className="section-heading"><div><h2>آخر المستندات</h2><p>أحدث الإضافات إلى مساحة الأرشيف</p></div><Link href="/documents" className="text-link">جميع المستندات<Icon name="arrow" /></Link></div>{recent.loading ? <Loading /> : recent.error ? <Failure message={recent.error} retry={recent.reload} /> : recent.data?.items.length ? <DocumentTable documents={recent.data.items} /> : <Empty />}</section>
  </>;
}
