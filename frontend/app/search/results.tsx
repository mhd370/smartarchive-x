"use client";
import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import type { Category, SearchItem, SearchResult } from "@/lib/api";
import { useApi } from "@/lib/use-api";
import { date, number, sources } from "@/lib/format";
import { Icon } from "@/components/icons";
import { CategoryBadge, Failure, FileSymbol, Loading, StatusBadge } from "@/components/ui";

const PAGE_SIZE = 20;

export default function SearchResults() {
  const params = useSearchParams(), router = useRouter();
  const query = (params.get("q") || "").trim(), category = params.get("category") || "";
  const mode = params.get("mode") === "exact" ? "exact" : "ranked";
  const categories = useApi<{ items: Category[] }>("/categories");
  const parsed = Number(params.get("offset") || 0), offset = Number.isFinite(parsed) && parsed >= 0 ? Math.floor(parsed) : 0;
  const [input, setInput] = useState(query);
  useEffect(() => { setInput(query); }, [query]);
  const request = new URLSearchParams({ q: query, limit: String(PAGE_SIZE), offset: String(offset) });
  if (category) request.set("category", category);
  if (mode === "exact") request.set("mode", "exact");
  const resource = useApi<SearchResult>(query ? `/search?${request}` : null);

  function go(q: string, at = 0, cat = category, how: string = mode) {
    const next = new URLSearchParams({ q });
    if (cat) next.set("category", cat);
    if (how === "exact") next.set("mode", "exact");
    if (at) next.set("offset", String(at));
    router.push(`/search?${next}`);
  }
  function submit(event: FormEvent) { event.preventDefault(); if (input.trim()) go(input.trim()); }

  return <>
    <div className="page-heading"><div><span className="eyebrow">البحث</span><h1>البحث في نصوص المستندات</h1>
      <p>يبحث في النص المستخرج والمصحَّح لكل صفحة وفي أسماء الملفات، ويتجاهل اختلاف الهمزات والتاء المربوطة والتشكيل.
        البحث الذكي يرتّب النتائج حسب الصلة ويجد الكلمة رغم السوابق واللواحق وأخطاء القراءة الآلية.</p></div></div>
    <section className="panel">
      <form className="filter-bar" onSubmit={submit} role="search">
        <div className="table-search search-box"><Icon name="search" />
          <input aria-label="كلمات البحث" placeholder="مثال: قرار إداري، أو &quot;عبارة كاملة&quot; بين علامتي تنصيص" value={input} maxLength={200} onChange={e => setInput(e.target.value)} />
          <button className="button primary compact" type="submit" disabled={!input.trim()}>بحث</button></div>
        <select aria-label="تصفية التصنيف" value={category} onChange={e => go(query || input.trim(), 0, e.target.value)}>
          <option value="">جميع التصنيفات</option>
          {categories.data?.items.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select>
        <select aria-label="طريقة البحث" value={mode} onChange={e => go(query || input.trim(), 0, category, e.target.value)}>
          <option value="ranked">بحث ذكي (حسب الصلة)</option>
          <option value="exact">كل الكلمات حرفيًا</option></select>
      </form>
      {!query ? <div className="empty-state"><div className="empty-icon"><Icon name="search" /></div><h3>ابحث داخل المستندات</h3>
        <p>اكتب كلمة أو أكثر؛ تظهر المستندات الأقرب أولًا مع مقاطع منها والصفحة التي وردت فيها. لاشتراط كل الكلمات اختر «كل الكلمات حرفيًا».</p></div>
        : resource.loading ? <Loading label="جار البحث…" /> : resource.error ? <Failure message={resource.error} retry={resource.reload} />
        : resource.data && <>
          <div className="search-summary">
            {resource.data.total ? <>{number(resource.data.total)} مستند يطابق «<span dir="auto">{query}</span>»</> : <>لا توجد مستندات تحتوي «<span dir="auto">{query}</span>»</>}
            {resource.data.truncated && <span className="neutral-tag">عدد المطابقات كبير؛ ضيّق البحث بكلمات إضافية</span>}
          </div>
          {resource.data.total === 0 ? <div className="empty-state"><div className="empty-icon"><Icon name="search" /></div><h3>لا توجد نتائج مطابقة</h3>
            <p>جرّب كلمات أقل أو جزءًا من الكلمة. النصوص الآلية قد تحتوي أخطاء قراءة؛ تصحيحها من صفحة المستند يحسّن البحث.</p></div>
            : <ol className="search-results">{resource.data.items.map(item => <Result key={item.document.id} item={item} query={query} />)}</ol>}
          {resource.data.total > PAGE_SIZE && <div className="pagination">
            <span>عرض {number(offset + 1)}–{number(offset + resource.data.items.length)} من {number(resource.data.total)}</span>
            <div><button className="button secondary compact" disabled={offset === 0} onClick={() => go(query, Math.max(0, offset - PAGE_SIZE))}>السابق</button>
              <button className="button secondary compact" disabled={offset + resource.data.items.length >= resource.data.total} onClick={() => go(query, offset + PAGE_SIZE)}>التالي</button></div>
          </div>}
        </>}
    </section>
  </>;
}

function Result({ item, query }: { item: SearchItem; query: string }) {
  const doc = item.document;
  return <li className="search-result">
    <div className="result-head">
      <Link href={`/documents/${doc.id}`} className="document-name"><FileSymbol mime={doc.mime_type} />
        <span><strong dir="auto">{doc.filename}</strong><small>{date(doc.created_at)} · {number(doc.page_count)} صفحة</small></span></Link>
      <span className="result-tags"><CategoryBadge name={doc.category_name} state={doc.category_state} /><StatusBadge status={doc.status} /></span>
    </div>
    {item.filename_match && <p className="match-note"><Icon name="file" />الكلمات واردة في اسم الملف.</p>}
    {item.pages.map(page => <div key={page.page_no} className="page-hit">
      <div className="page-hit-head">
        <Link className="text-link" href={`/documents/${doc.id}?${new URLSearchParams({ page: String(page.page_no), q: query })}`}>الصفحة {number(page.page_no)}<Icon name="arrow" /></Link>
        <span className={`source-tag source-${page.source}`}>{sources[page.source]}</span>
        <span className="muted">{page.match_count ? `${number(page.match_count)} تطابق` : "تطابق تقريبي"}</span>
      </div>
      {page.snippets.map((parts, index) => <p key={index} className="snippet" dir="auto">
        {parts.map((part, i) => part.match ? <mark key={i}>{part.text}</mark> : <span key={i}>{part.text}</span>)}</p>)}
    </div>)}
    {item.matched_pages > item.pages.length && <p className="muted more-pages">و{number(item.matched_pages - item.pages.length)} صفحات أخرى مطابقة.</p>}
  </li>;
}
