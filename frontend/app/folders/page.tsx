"use client";
import { useState } from "react";
import type { FormEvent } from "react";
import Link from "next/link";
import { post, type Folder } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useApi } from "@/lib/use-api";
import { actors, date, number } from "@/lib/format";
import { Icon } from "@/components/icons";
import { Failure, Loading } from "@/components/ui";
import { FolderGraphPanel } from "@/components/folder-graph";

export default function Folders() {
  const { can } = useAuth();
  const resource = useApi<{ items: Folder[] }>("/folders");
  const [name, setName] = useState(""), [parent, setParent] = useState("");
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  async function create(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try { await post("/folders", { name, parent_id: parent || null }); setName(""); resource.reload(); }
    catch (failure) { setError(failure instanceof Error ? failure.message : "تعذر إنشاء المجلد."); }
    finally { setBusy(false); }
  }
  return <>
    <div className="page-heading"><div><span className="eyebrow">التنظيم</span><h1>المجلدات</h1>
      <p>شجرة الأرشيف. يُستخدم مجلد المستند دليلًا إضافيًا في التصنيف والبحث، وكل نقل بين المجلدات يُسجَّل.</p></div></div>
    {can("documents.upload") && <section className="panel">
      <form className="filter-bar folder-form" onSubmit={create}>
        <label className="sr-only" htmlFor="folder-name">اسم المجلد الجديد</label>
        <input id="folder-name" className="text-input" placeholder="اسم المجلد الجديد" value={name} maxLength={120} onChange={e => setName(e.target.value)} required />
        <label className="sr-only" htmlFor="folder-parent">داخل المجلد</label>
        <select id="folder-parent" value={parent} onChange={e => setParent(e.target.value)}>
          <option value="">في الجذر</option>
          {resource.data?.items.map(item => <option key={item.id} value={item.id}>{"\u00a0".repeat(item.depth * 3)}{item.name}</option>)}
        </select>
        <button className="button primary compact" type="submit" disabled={busy || !name.trim()}><Icon name="folder" />إنشاء مجلد</button>
      </form>
      {error && <Failure message={error} />}
      <p className="muted small-note folder-hint">لاستيراد مجلد كامل بمجلداته الفرعية: <span dir="ltr" className="code-inline">tools\import_tree.py D:\scans --into "اسم المجلد"</span></p>
    </section>}
    <section className="panel">
      {resource.loading ? <Loading /> : resource.error ? <Failure message={resource.error} retry={resource.reload} /> :
        resource.data!.items.length === 0 ? <div className="empty-state"><div className="empty-icon"><Icon name="folder" /></div><h3>لا توجد مجلدات بعد</h3><p>أنشئ مجلدًا أو استورد شجرة مجلدات.</p></div> :
        <ul className="folder-tree">{resource.data!.items.map(item => <li key={item.id} style={{ paddingInlineStart: `${24 + item.depth * 26}px` }}>
          <Link href={`/documents?folder=${item.id}`} className="folder-link"><Icon name="folder" /><span dir="auto">{item.name}</span></Link>
          <span className="muted">{number(item.documents)} مستند{item.total_documents > item.documents && ` · ${number(item.total_documents)} مع الفرعية`}</span>
          <small className="muted">{actors(item.created_by)} · {date(item.created_at)}</small>
        </li>)}</ul>}
    </section>
    <FolderGraphPanel />
  </>;
}
