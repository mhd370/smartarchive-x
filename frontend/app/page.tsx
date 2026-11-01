"use client";
import Link from "next/link";
import { useApi } from "@/lib/use-api";
import type { Statistics, DocumentList, Status } from "@/lib/api";
import { bytes, number, statuses } from "@/lib/format";
import { Icon } from "@/components/icons";
import { DocumentTable, Empty, Failure, Loading } from "@/components/ui";
import { Can } from "@/components/can";

export default function Dashboard() {
  const stats = useApi<Statistics>("/statistics"), recent = useApi<DocumentList>("/documents?limit=5");
  return <>
    <div className="page-heading"><div><span className="eyebrow">مساحة عمل المستندات</span><h1>نظرة عامة على أرشيفك</h1><p>تابع مستنداتك وحالتها من مكان واحد.</p></div><button className="button secondary" onClick={() => { stats.reload(); recent.reload(); }}><Icon name="refresh" />تحديث البيانات</button></div>
    <section className="welcome-panel"><div><span className="section-kicker"><span />حفظ موثوق للمستندات</span><h2>كل مستند له مكان.<br />وكل أصل يبقى محفوظًا.</h2><p>ارفع مستنداتك العربية، استعرض بياناتها، وارجع إلى الأصل متى احتجت إليه.</p><Can permission="documents.upload"><Link href="/upload" className="button primary">إضافة مستند<Icon name="arrow" /></Link></Can></div><div className="archive-illustration" aria-hidden="true"><span className="orbit orbit-one" /><span className="orbit orbit-two" /><div className="illustrated-folder"><Icon name="archive" /><span /><span /><span /></div><div className="illustrated-check"><Icon name="check" /></div></div></section>
    {stats.loading ? <Loading label="جار تحميل إحصاءات الأرشيف…" /> : stats.error ? <Failure message={stats.error} retry={stats.reload} /> : stats.data && <>
      <section className="stats-grid" aria-label="إحصاءات الأرشيف"><article className="stat-card"><span className="stat-icon"><Icon name="file" /></span><span>إجمالي المستندات</span><strong data-testid="document-count">{number(stats.data.total_documents)}</strong><small>جميع المستندات المسجلة</small></article><article className="stat-card"><span className="stat-icon mint"><Icon name="shield" /></span><span>الأصول المحفوظة</span><strong>{number(stats.data.by_status.stored)}</strong><small>محفوظة وتنتظر تكامل المعالجة</small></article><article className="stat-card"><span className="stat-icon sand"><Icon name="archive" /></span><span>حجم الأرشيف</span><strong className="size-value">{bytes(stats.data.total_bytes)}</strong><small>الحجم الفعلي للملفات الأصلية</small></article></section>
      <section className="panel status-panel"><div className="section-heading"><div><h2>حالة المستندات</h2><p>الحالات المسجلة فعليًا في قاعدة البيانات</p></div><span className="neutral-tag">المعالجة الآلية غير مفعلة</span></div><div className="status-breakdown">{(Object.keys(statuses) as Status[]).map(status => <div key={status}><span className={`status-dot dot-${status}`} /><span>{statuses[status]}</span><strong>{number(stats.data!.by_status[status])}</strong></div>)}</div></section>
    </>}
    <section className="panel"><div className="section-heading"><div><h2>آخر المستندات</h2><p>أحدث الإضافات إلى مساحة الأرشيف</p></div><Link href="/documents" className="text-link">جميع المستندات<Icon name="arrow" /></Link></div>{recent.loading ? <Loading /> : recent.error ? <Failure message={recent.error} retry={recent.reload} /> : recent.data?.items.length ? <DocumentTable documents={recent.data.items} /> : <Empty />}</section>
  </>;
}
