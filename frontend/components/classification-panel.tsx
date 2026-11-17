"use client";
import { useState } from "react";
import type { FormEvent } from "react";
import { post, type Category, type Classification } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useApi } from "@/lib/use-api";
import { actors, categoryStates, date, number, percent, suggestionOutcomes } from "@/lib/format";
import { Icon } from "./icons";
import { CategoryBadge, Failure, Loading } from "./ui";

/** Current category, the classifier's explained suggestion, and human confirmation or reclassification. */
export function ClassificationPanel({ documentId, onChanged }: { documentId: string; onChanged?: () => void }) {
  const { can } = useAuth();
  const resource = useApi<Classification>(`/documents/${documentId}/classification`);
  const categories = useApi<{ items: Category[] }>("/categories");
  const groups = useApi<{ items: { id: string; name: string }[] }>("/category-groups");
  const groupNames: Record<string, string> = Object.fromEntries((groups.data?.items ?? []).map(item => [item.id, item.name]));
  const [choice, setChoice] = useState(""), [reason, setReason] = useState("");
  const [editing, setEditing] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState("");

  async function send(path: string, body?: unknown) {
    setBusy(true); setError("");
    try { await post(path, body); setEditing(false); setReason(""); resource.reload(); onChanged?.(); }
    catch (failure) { setError(failure instanceof Error ? failure.message : "تعذر حفظ التصنيف."); }
    finally { setBusy(false); }
  }
  function decide(categoryId: string) {
    return send(`/documents/${documentId}/classification`,
      { category_id: categoryId, expected_sequence: resource.data!.sequence, reason });
  }
  function submit(event: FormEvent) { event.preventDefault(); if (choice) void decide(choice); }

  if (resource.loading) return <section className="panel classification-panel"><Loading /></section>;
  if (resource.error) return <section className="panel classification-panel"><Failure message={resource.error} retry={resource.reload} /></section>;
  const data = resource.data!;
  const suggestion = data.suggestion, decision = data.decision, proposal = data.reclassification;
  const names = new Map((categories.data?.items ?? []).map(item => [item.id, item.name]));
  const evidence = suggestion?.category_id ? suggestion.evidence?.[suggestion.category_id] ?? [] : [];
  const candidates = Object.entries(suggestion?.scores ?? {}).slice(0, 3);
  const writer = can("review.write");
  const canConfirm = writer && data.state === "suggested" && suggestion?.category_id;
  const active = (categories.data?.items ?? []).filter(item => item.active && item.id !== decision?.category_id);

  return <section className="panel classification-panel" aria-labelledby="classification-heading">
    <div className="section-heading compact-heading">
      <h2 id="classification-heading">التصنيف</h2>
      <CategoryBadge name={data.category_name} state={data.state} />
    </div>
    {data.state === "none" && <p className="muted">لم يُقترح تصنيف بعد؛ يُقترح تلقائيًا بعد استخراج النص.</p>}
    {decision && <p className="classification-line"><Icon name="check" />
      اعتمده <span dir="auto">{actors(decision.actor)}</span> · {date(decision.created_at)}{decision.reason && <> · <span dir="auto">{decision.reason}</span></>}</p>}
    {proposal && <div className="reclassification-box" role="status">
      <p><Icon name="tag" /> <b>أدلة جديدة تقترح إعادة التصنيف:</b> من «{names.get(proposal.from_category_id) ?? proposal.from_category_id}»
        إلى «{names.get(proposal.to_category_id) ?? proposal.to_category_id}» (حصة {percent(proposal.share)} مقابل {percent(proposal.current_share)}).
        التصنيف المعتمد لا يتغيّر إلا بقرارك.</p>
      {writer && !editing && <div className="classification-actions">
        <button className="button primary compact" disabled={busy} onClick={() => { setEditing(true); setChoice(proposal.to_category_id); setReason("قبول اقتراح إعادة التصنيف بعد أدلة جديدة"); setError(""); }}>
          <Icon name="check" />مراجعة وقبول</button>
        <button className="button secondary compact" disabled={busy} onClick={() => send(`/documents/${documentId}/classification/reclassification/dismiss`, { suggestion_id: proposal.suggestion_id, reason: "" })}>
          إبقاء التصنيف الحالي</button>
      </div>}
    </div>}
    {suggestion && <div className="suggestion-box">
      <div className="suggestion-head">
        <span>اقتراح النظام: <b>{suggestion.category_name ?? "لا يوجد (غير مؤكد)"}</b></span>
        {suggestion.confidence !== null && <span className="confidence tone-fair">ثقة {percent(suggestion.confidence)}</span>}
      </div>
      <p className="muted small-note">{suggestionOutcomes[suggestion.reason] ?? suggestion.reason}</p>
      {typeof suggestion.basis.group_id === "string" && <p className="group-line">المستوى الأول: <b>{groupNames[suggestion.basis.group_id] ?? suggestion.basis.group_id}</b>
        {typeof suggestion.basis.group_confidence === "number" && ` · ثقة ${percent(suggestion.basis.group_confidence)}`}
        {!suggestion.category_id && " · النوع الفرعي غير مؤكد ويحتاج مراجعة"}</p>}
      {suggestion.basis.image_used === true && <p className="muted small-note">بُني على النص وشكل الصفحة الأولى معًا (جداول، أعمدة، ترويسة).</p>}
      {evidence.length > 0 && <ul className="keyword-list" aria-label="الكلمات التي بُني عليها الاقتراح">
        {evidence.slice(0, 6).map(hit => <li key={hit.keyword}><span dir="auto">{hit.keyword}</span>
          <small>{hit.count ? `×${number(hit.count)}` : ""}{hit.heading ? " · في العنوان" : ""}{hit.filename ? " · في اسم الملف" : ""}</small></li>)}
      </ul>}
      {!suggestion.category_id && candidates.length > 0 && <p className="muted small-note">أقرب الفئات: {candidates.map(([id, score]) => `${names.get(id) ?? id} (${number(score)})`).join("، ")}</p>}
    </div>}
    {error && <Failure message={error} />}
    {writer && <div className="classification-actions">
      {canConfirm && !editing && <button className="button primary compact" disabled={busy} onClick={() => decide(suggestion!.category_id!)}>
        <Icon name="check" />اعتماد «{suggestion!.category_name}»</button>}
      {!editing && <button className="button secondary compact" disabled={busy} onClick={() => { setEditing(true); setChoice(""); setError(""); }}>
        <Icon name="tag" />{decision ? "إعادة التصنيف" : "اختيار فئة أخرى"}</button>}
      {!editing && <button className="button secondary compact" disabled={busy} onClick={() => send(`/documents/${documentId}/classification/suggest`)}>
        <Icon name="refresh" />إعادة الاقتراح</button>}
    </div>}
    {editing && <form className="review-form classification-form" onSubmit={submit}>
      <label htmlFor="category-choice">الفئة</label>
      <select id="category-choice" value={choice} onChange={e => setChoice(e.target.value)} required>
        <option value="">اختر فئة…</option>
        {active.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
      </select>
      <label htmlFor="category-reason">السبب {decision ? "(مطلوب لإعادة التصنيف)" : "(اختياري)"}</label>
      <input id="category-reason" dir="auto" value={reason} maxLength={500} required={Boolean(decision)}
        onChange={e => setReason(e.target.value)} placeholder="مثال: المستند كتاب مرفق بقرار" />
      <div className="form-actions">
        <button className="button primary compact" type="submit" disabled={busy || !choice}>حفظ التصنيف</button>
        <button className="button secondary compact" type="button" disabled={busy} onClick={() => setEditing(false)}>إلغاء</button>
      </div>
    </form>}
    {data.history.length > 0 && <details className="revisions">
      <summary>سجل التصنيف ({number(data.history.length)})</summary>
      <ol>{data.history.map(item => <li key={item.id}>
        <span>{item.kind === "decision" ? "قرار بشري" : "اقتراح آلي"}: {item.category_name ?? categoryStates.uncertain}
          {item.confidence !== null && ` · ${percent(item.confidence)}`} · <span dir="auto">{actors(item.actor)}</span> · {date(item.created_at)}
          {item.reason && item.kind === "decision" && <> · <span dir="auto">{item.reason}</span></>}</span>
      </li>)}</ol>
    </details>}
  </section>;
}
