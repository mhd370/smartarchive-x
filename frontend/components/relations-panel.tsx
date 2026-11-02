"use client";
import { useState } from "react";
import Link from "next/link";
import { post, type Relation } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useApi } from "@/lib/use-api";
import { date, percent } from "@/lib/format";
import { Icon } from "./icons";
import { Failure, Loading } from "./ui";

const kinds = { exact_duplicate: "نسخة مطابقة (الملف نفسه)", near_duplicate: "شبه مطابق (النص نفسه تقريبًا)", version_of: "نسخة مختلفة من الوثيقة" };
const statuses = { suggested: "مقترح", confirmed: "مؤكد", rejected: "مرفوض" };

/** Duplicates and versions found by fingerprints; a reviewer confirms or rejects each link. */
export function RelationsPanel({ documentId }: { documentId: string }) {
  const { can } = useAuth();
  const resource = useApi<{ items: Relation[] }>(`/documents/${documentId}/relations`);
  const [busy, setBusy] = useState(""), [error, setError] = useState("");
  async function review(id: string, status: "confirmed" | "rejected") {
    setBusy(id); setError("");
    try { await post(`/relations/${id}/review`, { status }); resource.reload(); }
    catch (failure) { setError(failure instanceof Error ? failure.message : "تعذر حفظ المراجعة."); }
    finally { setBusy(""); }
  }
  if (resource.loading || resource.error || !resource.data?.items.length) return resource.error ? <Failure message={resource.error} retry={resource.reload} /> : resource.loading ? <Loading /> : null;
  return <section className="panel relations-panel" aria-labelledby="relations-heading">
    <div className="section-heading compact-heading"><h2 id="relations-heading">وثائق مكررة أو نسخ أخرى</h2></div>
    <ul>{resource.data.items.map(item => <li key={item.id} className={`relation-${item.status}`}>
      <div><strong>{kinds[item.kind]}</strong> · <span className="muted">تشابه {percent(item.score)} · {statuses[item.status]}</span></div>
      <Link className="text-link" href={`/documents/${item.other_id}`} dir="auto">{item.other_filename}<Icon name="arrow" /></Link>
      {item.other_created_at && <small className="muted"> أضيف {date(item.other_created_at)}</small>}
      {can("review.write") && item.status === "suggested" && <div className="relation-actions">
        <button className="button secondary compact" disabled={busy === item.id} onClick={() => review(item.id, "confirmed")}><Icon name="check" />تأكيد</button>
        <button className="button secondary compact" disabled={busy === item.id} onClick={() => review(item.id, "rejected")}><Icon name="close" />رفض</button>
      </div>}
    </li>)}</ul>
    {error && <Failure message={error} />}
  </section>;
}
