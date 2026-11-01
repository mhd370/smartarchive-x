"use client";
import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { get, post, type PageText, type RevisionText } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useApi } from "@/lib/use-api";
import { actors, date, number, percent, sources } from "@/lib/format";
import { Icon } from "./icons";
import { Failure, Loading } from "./ui";

/** The page text that search uses, with human correction and its version history. */
export function PageReview({ documentId, page, onSaved }: { documentId: string; page: number; onSaved?: () => void }) {
  const { can } = useAuth();
  const resource = useApi<PageText>(`/documents/${documentId}/pages/${page}/text`);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(""), [note, setNote] = useState("");
  const [saving, setSaving] = useState(false), [error, setError] = useState(""), [saved, setSaved] = useState(false);
  const [old, setOld] = useState<RevisionText>(), [oldError, setOldError] = useState("");

  useEffect(() => { setEditing(false); setError(""); setSaved(false); setOld(undefined); }, [documentId, page]);

  function startEdit() {
    setDraft(resource.data?.text ?? ""); setNote(""); setError(""); setSaved(false); setEditing(true);
  }
  async function save(event: FormEvent) {
    event.preventDefault();
    if (!resource.data) return;
    setSaving(true); setError("");
    try {
      await post<PageText>(`/documents/${documentId}/pages/${page}/text`,
        { text: draft, expected_version: resource.data.version, note });
      setEditing(false); setSaved(true); resource.reload(); onSaved?.();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "تعذر حفظ التصحيح.");
    } finally { setSaving(false); }
  }
  async function show(version: number) {
    setOldError("");
    try { setOld(await get<RevisionText>(`/documents/${documentId}/pages/${page}/revisions/${version}`)); }
    catch (failure) { setOldError(failure instanceof Error ? failure.message : "تعذر تحميل النسخة."); }
  }

  if (resource.loading) return <section className="panel review-panel"><Loading /></section>;
  if (resource.error) return <section className="panel review-panel"><Failure message={resource.error} retry={resource.reload} /></section>;
  const data = resource.data!;
  const latest = data.revisions[0];
  return <section className="panel review-panel" aria-labelledby="review-heading">
    <div className="section-heading">
      <div><h2 id="review-heading">النص المعتمد · الصفحة {number(page)}</h2>
        <p>هذا النص هو ما يظهر في البحث. التصحيح يُحفظ كنسخة جديدة باسمك ولا يحذف ما قبله.</p></div>
      <div className="review-actions">
        {data.source && <span className={`source-tag source-${data.source}`}>{sources[data.source]}</span>}
        {can("review.write") && data.available && !editing &&
          <button className="button secondary compact" onClick={startEdit}><Icon name="edit" />تصحيح النص</button>}
      </div>
    </div>
    {!data.available ? <p className="muted">{data.blank ? "صُنّفت هذه الصفحة فارغة؛ لا يوجد نص لاعتماده." : "لا يوجد نص مستخرج لهذه الصفحة بعد."}</p> : <>
      {data.review_required && !data.reviewed && <div className="review-flag"><Icon name="alert" />
        ثقة OCR لهذه الصفحة {percent(data.ocr_confidence)}؛ تحتاج مراجعة بشرية قبل اعتماد نصها.</div>}
      {saved && <div role="status" className="saved-note"><Icon name="check" />حُفظ التصحيح كنسخة {number(data.version)}، وأصبح النص المصحح قابلًا للبحث.</div>}
      {latest && !editing && <p className="revision-line">آخر تصحيح: نسخة {number(latest.version)} · <span dir="auto">{actors(latest.author)}</span> · {date(latest.created_at)}{latest.note && <> · <span dir="auto">{latest.note}</span></>}</p>}
      {editing ? <form className="review-form" onSubmit={save}>
        <label htmlFor="page-text">نص الصفحة بعد التصحيح</label>
        <textarea id="page-text" dir="auto" value={draft} onChange={e => setDraft(e.target.value)} rows={Math.min(18, Math.max(6, draft.split("\n").length + 1))} maxLength={100000} />
        <label htmlFor="review-note">ملاحظة (اختيارية)</label>
        <input id="review-note" dir="auto" value={note} onChange={e => setNote(e.target.value)} maxLength={500} placeholder="مثال: تصحيح الأسماء والأرقام" />
        {error && <Failure message={error} retry={error.includes("شخص آخر") ? () => { resource.reload(); setEditing(false); } : undefined} />}
        <div className="form-actions">
          <button className="button primary" type="submit" disabled={saving || draft.trim() === (data.text ?? "").trim()}>
            <Icon name="check" />{saving ? "جار الحفظ…" : "حفظ التصحيح"}</button>
          <button className="button secondary" type="button" onClick={() => setEditing(false)} disabled={saving}>إلغاء</button>
        </div>
      </form> : <pre className="page-text" dir="auto">{data.text || "—"}</pre>}
      {data.revisions.length > 0 && <details className="revisions">
        <summary>سجل التصحيحات ({number(data.revisions.length)})</summary>
        <ol>{data.revisions.map(item => <li key={item.id}>
          <span>نسخة {number(item.version)} · <span dir="auto">{actors(item.author)}</span> · {date(item.created_at)} · {number(item.characters)} حرفًا
            {item.note && <> · <span dir="auto">{item.note}</span></>}</span>
          <button type="button" className="text-button" onClick={() => show(item.version)}>عرض النص</button>
        </li>)}</ol>
        {oldError && <Failure message={oldError} />}
        {old && <div className="old-revision"><strong>نص النسخة {number(old.version)}</strong>
          <pre className="page-text" dir="auto">{old.text}</pre></div>}
      </details>}
    </>}
  </section>;
}
