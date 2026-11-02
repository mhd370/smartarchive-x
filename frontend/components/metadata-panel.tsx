"use client";
import { useState } from "react";
import type { FormEvent } from "react";
import { put, type MetadataResult } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useApi } from "@/lib/use-api";
import { actors, number, percent } from "@/lib/format";
import { Icon } from "./icons";
import { Failure, Loading } from "./ui";

const labels: Record<string, string> = { reference_number: "رقم الكتاب / المرجع", date: "التاريخ", sender: "المرسل",
  recipient: "المرسل إليه", subject: "الموضوع", amount: "المبلغ" };

/** Extracted metadata with its source; reviewers correct a field and the correction always wins. */
export function MetadataPanel({ documentId, onChanged }: { documentId: string; onChanged?: () => void }) {
  const { can } = useAuth();
  const resource = useApi<MetadataResult>(`/documents/${documentId}/metadata`);
  const [editing, setEditing] = useState<string>(), [value, setValue] = useState("");
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  async function save(event: FormEvent) {
    event.preventDefault(); if (!editing) return;
    setBusy(true); setError("");
    try { await put(`/documents/${documentId}/metadata/${editing}`, { value }); setEditing(undefined); resource.reload(); onChanged?.(); }
    catch (failure) { setError(failure instanceof Error ? failure.message : "تعذر حفظ القيمة."); }
    finally { setBusy(false); }
  }
  if (resource.loading) return <section className="panel metadata-fields"><Loading /></section>;
  if (resource.error) return <section className="panel metadata-fields"><Failure message={resource.error} retry={resource.reload} /></section>;
  const data = resource.data!;
  return <section className="panel metadata-fields" aria-labelledby="metadata-heading">
    <div className="section-heading compact-heading"><h2 id="metadata-heading">البيانات الوصفية</h2>
      <span className="neutral-tag" dir="ltr">{data.method}</span></div>
    {!data.extracted && <p className="muted">تُستخرج تلقائيًا بعد استخراج النص.</p>}
    <dl>{Object.values(data.fields).map(item => <div key={item.field} className="metadata-row">
      <dt>{labels[item.field] ?? item.field}{item.protected && <span className="lock-note" title="حقل محمي: لا يصححه النظام آليًا"><Icon name="lock" /></span>}</dt>
      {editing === item.field ? <dd><form className="inline-edit" onSubmit={save}>
        <input aria-label={labels[item.field]} dir="auto" value={value} onChange={e => setValue(e.target.value)} maxLength={200} autoFocus />
        <button className="button primary compact" type="submit" disabled={busy}>حفظ</button>
        <button className="button secondary compact" type="button" onClick={() => setEditing(undefined)} disabled={busy}>إلغاء</button>
      </form></dd> : <dd>
        <span dir="auto">{item.value ?? <span className="muted">—</span>}</span>
        {item.value && item.field === "date" && item.normalized && item.normalized !== item.value && <small className="muted" dir="ltr"> {item.normalized}</small>}
        <small className="muted metadata-source">{item.source === "human" ? `صُحّح بواسطة ${actors(item.actor ?? "")}` : item.source === "extracted" ? `مستخرج آليًا · ثقة ${percent(item.confidence)}${item.page_no ? ` · ص ${number(item.page_no)}` : ""}` : ""}</small>
        {can("review.write") && <button className="text-button" onClick={() => { setEditing(item.field); setValue(item.value ?? ""); setError(""); }} aria-label={`تعديل ${labels[item.field]}`}><Icon name="edit" /></button>}
      </dd>}
    </div>)}</dl>
    {error && <Failure message={error} />}
  </section>;
}
