"use client";
import { useState } from "react";
import Link from "next/link";
import { apiUrl, post, type BackupItem, type BackupVerification, type IntegrityReport } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useApi } from "@/lib/use-api";
import { actors, bytes, date, number } from "@/lib/format";
import { Icon } from "@/components/icons";
import { Failure, Loading } from "@/components/ui";

const problems: Record<string, string> = { original_missing: "الأصل مفقود", checksum_mismatch: "البصمة لا تطابق (الملف تغيّر أو تلف)" };

export default function SystemPage() {
  const { can } = useAuth();
  const admin = can("users.manage");
  const list = useApi<{ items: BackupItem[]; directory: string }>(admin ? "/admin/backups" : null);
  const [busy, setBusy] = useState(""), [error, setError] = useState("");
  const [checks, setChecks] = useState<Record<string, BackupVerification>>({});
  const [report, setReport] = useState<IntegrityReport>();

  async function run<T>(key: string, action: () => Promise<T>, done: (value: T) => void) {
    setBusy(key); setError("");
    try { done(await action()); } catch (failure) { setError(failure instanceof Error ? failure.message : "تعذر تنفيذ العملية."); }
    finally { setBusy(""); }
  }
  if (!admin) return <section className="panel"><div className="empty-state"><div className="empty-icon"><Icon name="lock" /></div><h3>هذه الصفحة لمدير النظام</h3></div></section>;
  return <>
    <div className="page-heading"><div><span className="eyebrow">التشغيل</span><h1>النظام والنسخ الاحتياطي</h1>
      <p>نسخة احتياطية كاملة (قاعدة البيانات وكل الأصول مع بصماتها)، والتحقق منها، وفحص سلامة الأرشيف.</p></div></div>
    {error && <Failure message={error} />}
    <section className="panel">
      <div className="section-heading"><div><h2>النسخ الاحتياطية</h2>
        <p>تُحفظ في <span dir="ltr" className="code-inline">{list.data?.directory ?? "…"}</span>. انسخها أيضًا إلى قرص آخر؛ نسخة على القرص نفسه لا تحمي من تلفه.</p></div>
        <button className="button primary" disabled={!!busy} onClick={() => run("create", () => post<BackupItem>("/admin/backups"), () => list.reload())}>
          <Icon name="database" />{busy === "create" ? "جار إنشاء النسخة…" : "إنشاء نسخة احتياطية"}</button></div>
      {list.loading ? <Loading /> : list.error ? <Failure message={list.error} retry={list.reload} /> :
        list.data!.items.length === 0 ? <div className="empty-state"><div className="empty-icon"><Icon name="database" /></div><h3>لا توجد نسخ احتياطية بعد</h3>
          <p>أنشئ أول نسخة الآن، ثم تحقق منها ونزّلها إلى مكان آخر.</p></div> :
        <div className="table-scroll"><table><thead><tr><th>النسخة</th><th>المستندات</th><th>الحجم</th><th>أنشأها</th><th>التحقق</th><th><span className="sr-only">إجراءات</span></th></tr></thead>
          <tbody>{list.data!.items.map(item => { const check = checks[item.name]; return <tr key={item.name}>
            <td><strong dir="ltr" className="backup-name">{item.name}</strong><small className="block muted">{item.created_at ? date(item.created_at) : date(item.modified_at)} · v{item.app_version || "?"} · مخطط {item.schema_version ?? "?"}</small></td>
            <td>{item.document_count === undefined ? "—" : number(item.document_count)}</td>
            <td className="nowrap">{bytes(item.size_bytes)}</td>
            <td dir="auto">{item.created_by ? actors(item.created_by) : "—"}</td>
            <td>{check ? check.ok ? <span className="confidence tone-good">سليمة</span> : <span className="confidence tone-low" title={check.problems.join("\n")}>{number(check.problem_count ?? check.problems.length)} مشكلة</span> : <span className="muted">لم تُفحص</span>}</td>
            <td className="row-actions"><button className="button secondary compact" disabled={!!busy}
              onClick={() => run(item.name, () => post<BackupVerification>(`/admin/backups/${item.name}/verify`), value => setChecks(old => ({ ...old, [item.name]: value })))}>
              <Icon name="shield" />{busy === item.name ? "جار التحقق…" : "تحقق"}</button>
              <a className="button secondary compact" href={apiUrl(`/admin/backups/${item.name}/download`)}><Icon name="download" />تنزيل</a></td>
          </tr>; })}</tbody></table></div>}
      <details className="steps-detail restore-help"><summary>الاستعادة من نسخة احتياطية</summary>
        <p>الاستعادة لا تكتب فوق الأرشيف الحالي أبدًا: تُستخرج النسخة بعد التحقق منها إلى مجلد جديد فارغ، ثم يُشغَّل الخادم عليه.</p>
        <pre dir="ltr">.\.venv\Scripts\python.exe tools\archive_ops.py restore storage\backups\NAME.zip D:\restored-storage{"\n"}$env:SMARTARCHIVE_STORAGE_DIR = "D:\restored-storage"</pre></details>
    </section>
    <section className="panel">
      <div className="section-heading"><div><h2>فحص سلامة الأرشيف</h2>
        <p>يعيد حساب بصمة كل أصل ويقارنها بقاعدة البيانات، ويفحص قاعدة البيانات والحماية من التعديل. لا يحذف ولا يصلح شيئًا.</p></div>
        <button className="button secondary" disabled={!!busy} onClick={() => run("integrity", () => post<IntegrityReport>("/admin/integrity"), setReport)}>
          <Icon name="refresh" />{busy === "integrity" ? "جار الفحص…" : "تشغيل الفحص"}</button></div>
      {report && <div className="integrity-report" role="status">
        <div className={report.ok ? "saved-note" : "review-flag"}><Icon name={report.ok ? "check" : "alert"} />
          {report.ok ? `الأرشيف سليم: فُحص ${number(report.documents_checked)} أصلًا وطابقت جميعها.` : "وُجدت مشكلات تحتاج متابعة."}
          {report.warnings > 0 && ` · ${number(report.warnings)} تنبيه`}</div>
        <dl className="quality-facts">
          <div><dt>قاعدة البيانات</dt><dd dir="ltr">{report.database}</dd></div>
          <div><dt>مخالفات المفاتيح</dt><dd>{number(report.foreign_key_violations)}</dd></div>
          <div><dt>حماية السجلات من التعديل</dt><dd>{report.missing_triggers.length ? `ناقصة: ${report.missing_triggers.join("، ")}` : "مفعّلة"}</dd></div>
          <div><dt>مجلدات أصول غير مرتبطة بمستند</dt><dd>{number(report.orphan_folders.length)}</dd></div>
          <div><dt>رفع غير مكتمل</dt><dd>{number(report.partial_uploads.length)}</dd></div>
          <div><dt>مستندات غير مفهرسة للبحث</dt><dd>{number(report.unindexed_documents)}</dd></div>
          <div><dt>وقت الفحص</dt><dd>{date(report.checked_at)}</dd></div>
        </dl>
        {report.document_problems.length > 0 && <ul className="problem-list">{report.document_problems.map(item => <li key={item.document_id}>
          <Link href={`/documents/${item.document_id}`} dir="auto">{item.filename}</Link> — {problems[item.problem] ?? item.problem}</li>)}</ul>}
      </div>}
    </section>
  </>;
}
