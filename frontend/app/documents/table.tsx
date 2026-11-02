"use client";
import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";
import { useApi } from "@/lib/use-api";
import type { Category, DocumentList, Folder, Status } from "@/lib/api";
import { number, statuses } from "@/lib/format";
import { Icon } from "@/components/icons";
import { DocumentTable, Empty, Failure, Loading } from "@/components/ui";
import { Can } from "@/components/can";

export default function Documents() {
  const search = useSearchParams(), router = useRouter();
  const query = search.get("q") || "", status = search.get("status") || "", kind = search.get("kind") || "", category = search.get("category") || "", folder = search.get("folder") || "";
  const parsed = Number(search.get("offset") || 0), offset = Number.isFinite(parsed) && parsed >= 0 ? Math.floor(parsed) : 0;
  const [input, setInput] = useState(query);
  useEffect(() => { setInput(query); }, [query]);
  const params = new URLSearchParams({ q: query, limit: "25", offset: String(offset) });
  if (status) params.set("status", status); if (kind) params.set("kind", kind); if (category) params.set("category", category); if (folder) params.set("folder", folder);
  const resource = useApi<DocumentList>(`/documents?${params}`);
  const categories = useApi<{ items: Category[] }>("/categories");
  const folders = useApi<{ items: Folder[] }>("/folders");
  function change(key: string, value: string) {
    const next = new URLSearchParams(search.toString());
    if (value) next.set(key, value); else next.delete(key);
    if (key !== "offset") next.delete("offset");
    router.push(`/documents?${next}`);
  }
  function submit(event: FormEvent) { event.preventDefault(); change("q", input.trim()); }
  return <><div className="page-heading"><div><span className="eyebrow">الأرشيف</span><h1>المستندات</h1><p>ابحث في أسماء المستندات واستعرض أصولها وبياناتها.</p></div><Can permission="documents.upload"><Link href="/upload" className="button primary"><Icon name="upload" />رفع مستند جديد</Link></Can></div><section className="panel"><div className="filter-bar"><form onSubmit={submit} className="table-search"><Icon name="search" /><input aria-label="اسم المستند" placeholder="ابحث باسم المستند…" value={input} maxLength={200} onChange={e => setInput(e.target.value)} /><button className="button secondary compact" type="submit">بحث</button></form><select aria-label="تصفية الحالة" value={status} onChange={e => change("status", e.target.value)}><option value="">جميع الحالات</option>{(Object.keys(statuses) as Status[]).map(key => <option value={key} key={key}>{statuses[key]}</option>)}</select><select aria-label="تصفية النوع" value={kind} onChange={e => change("kind", e.target.value)}><option value="">جميع الأنواع</option><option value="pdf">PDF</option><option value="image">صور</option></select><select aria-label="تصفية المجلد" value={folder} onChange={e => change("folder", e.target.value)}><option value="">جميع المجلدات</option>{folders.data?.items.map(item => <option key={item.id} value={item.id}>{"\u00a0".repeat(item.depth * 3)}{item.name} ({item.total_documents})</option>)}</select><select aria-label="تصفية التصنيف" value={category} onChange={e => change("category", e.target.value)}><option value="">جميع التصنيفات</option><option value="none">غير مصنّف</option>{categories.data?.items.map(item => <option key={item.id} value={item.id}>{item.name}{item.active ? "" : " (موقوفة)"}</option>)}</select><button className="icon-link" aria-label="تحديث المستندات" onClick={resource.reload}><Icon name="refresh" /></button></div>{resource.loading ? <Loading /> : resource.error ? <Failure message={resource.error} retry={resource.reload} /> : resource.data && <>{resource.data.items.length ? <DocumentTable documents={resource.data.items} /> : <Empty filtered={Boolean(query || status || kind || category || folder)} />}<div className="pagination"><span>{number(resource.data.total)} مستند {resource.data.items.length > 0 && `· عرض ${number(offset + 1)}–${number(offset + resource.data.items.length)}`}</span><div><button className="button secondary compact" disabled={offset === 0} onClick={() => change("offset", String(Math.max(0, offset - 25)))}>السابق</button><button className="button secondary compact" disabled={offset + resource.data.items.length >= resource.data.total} onClick={() => change("offset", String(offset + 25))}>التالي</button></div></div></>}</section></>;
}
