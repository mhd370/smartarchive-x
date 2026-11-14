"use client";
import { useState } from "react";
import Link from "next/link";
import type { FolderGraph } from "@/lib/api";
import { useApi } from "@/lib/use-api";
import { number } from "@/lib/format";
import { Failure, Loading } from "@/components/ui";

const kinds: Record<string, string> = { exact_duplicate: "نسخة مطابقة", near_duplicate: "نسخة شبه مطابقة", version_of: "إصدار" };
const ROW = 34, W = 720;

/** Folders on the right, categories on the left (RTL); a link's width is the number of documents of that
 * category in that folder, and solid when people confirmed most of them. Cross-folder relations are listed. */
export function FolderGraphPanel() {
  const resource = useApi<FolderGraph>("/graph");
  const [focus, setFocus] = useState<string | null | undefined>(undefined);
  if (resource.loading) return <section className="panel"><Loading /></section>;
  if (resource.error) return <section className="panel"><Failure message={resource.error} retry={resource.reload} /></section>;
  const graph = resource.data;
  if (!graph || graph.folder_category.length === 0) return null;
  const folders = graph.folders.filter(f => f.documents > 0), categories = graph.categories;
  const fy = new Map(folders.map((f, i) => [f.id, 24 + i * ROW])), cy = new Map(categories.map((c, i) => [c.id, 24 + i * ROW]));
  const height = 24 + Math.max(folders.length, categories.length) * ROW;
  const max = Math.max(...graph.folder_category.map(l => l.documents));
  const names = new Map(graph.folders.map(f => [f.id, f.name]));
  return <section className="panel" aria-labelledby="folder-graph">
    <div className="section-heading"><div><h2 id="folder-graph">خريطة الأرشيف</h2>
      <p>أي أنواع المستندات توجد في كل مجلد. سُمك الخط بعدد المستندات، والخط المتصل يعني أن معظمها مؤكَّد التصنيف بشريًا، والمتقطع أنه مقترح آليًا. مرّر على مجلد لإبراز روابطه.</p></div></div>
    <div className="graph-scroll">
      <svg viewBox={`0 0 ${W} ${height}`} className="folder-graph" role="img" aria-label="روابط المجلدات بأنواع المستندات">
        {graph.folder_category.map(link => {
          const y1 = fy.get(link.folder_id), y2 = cy.get(link.category_id);
          if (y1 === undefined || y2 === undefined) return null;
          const dim = focus !== undefined && focus !== link.folder_id;
          return <path key={`${link.folder_id}-${link.category_id}`} d={`M ${W - 210} ${y1} C ${W / 2} ${y1}, ${W / 2} ${y2}, 210 ${y2}`}
            className={`graph-link ${link.confirmed * 2 >= link.documents ? "confirmed" : "suggested"} ${dim ? "dim" : ""}`}
            strokeWidth={1.5 + 9 * link.documents / max}><title>{`${names.get(link.folder_id) ?? ""} ← ${categories.find(c => c.id === link.category_id)?.name}: ${link.documents} (مؤكد ${link.confirmed})`}</title></path>;
        })}
        {folders.map(f => <g key={f.id ?? "none"} className="graph-node folder" onMouseEnter={() => setFocus(f.id)} onMouseLeave={() => setFocus(undefined)}>
          <rect x={W - 205} y={(fy.get(f.id) ?? 0) - 13} width={200} height={26} rx={6} />
          <text x={W - 14} y={(fy.get(f.id) ?? 0) + 5} textAnchor="end">{f.name} · {number(f.documents)}</text></g>)}
        {categories.map(c => <g key={c.id} className="graph-node category">
          <rect x={5} y={(cy.get(c.id) ?? 0) - 13} width={200} height={26} rx={13} />
          <text x={196} y={(cy.get(c.id) ?? 0) + 5} textAnchor="end">{c.name} · {number(c.documents)}</text></g>)}
      </svg>
    </div>
    {graph.folder_relations.length > 0 && <>
      <h3 className="graph-subtitle">علاقات تعبر المجلدات</h3>
      <ul className="graph-relations">{graph.folder_relations.map((r, i) => <li key={i}>
        <b>{names.get(r.a) ?? "غير مصنّف في مجلد"}</b> ↔ <b>{names.get(r.b) ?? "غير مصنّف في مجلد"}</b>: {number(r.count)} {kinds[r.kind] ?? r.kind}</li>)}</ul>
      <p className="muted">نسخة أو إصدار في مجلد غير مجلد أصله قد يعني أن أحدهما محفوظ في المكان الخطأ. <Link className="text-link" href="/review">مراجعة العلاقات</Link></p>
    </>}
  </section>;
}
