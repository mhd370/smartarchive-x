"use client";
import { useState } from "react";
import type { FormEvent } from "react";
import Link from "next/link";
import { patch, post, type Category } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useApi } from "@/lib/use-api";
import { actors, date, number } from "@/lib/format";
import { Icon } from "@/components/icons";
import { Failure, Loading } from "@/components/ui";

const split = (value: string) => value.split(/[،,\n]/).map(word => word.trim()).filter(Boolean);

export default function Categories() {
  const { can } = useAuth();
  const admin = can("users.manage");
  const resource = useApi<{ items: Category[] }>("/categories");
  const [editing, setEditing] = useState<string>();
  const [adding, setAdding] = useState(false);
  return <>
    <div className="page-heading"><div><span className="eyebrow">التصنيف</span><h1>فئات المستندات</h1>
      <p>يقترح النظام فئة لكل مستند من كلماتها المفتاحية في نصه واسمه، ويعتمدها شخص مخوّل. الأرقام: معتمد / مقترح.</p></div>
      {admin && !adding && <button className="button primary" onClick={() => setAdding(true)}><Icon name="tag" />إضافة فئة</button>}</div>
    {adding && <CategoryForm onDone={() => { setAdding(false); resource.reload(); }} />}
    <section className="panel">
      {resource.loading ? <Loading /> : resource.error ? <Failure message={resource.error} retry={resource.reload} /> :
        <ul className="category-list">{resource.data!.items.map(item => <li key={item.id} className={item.active ? "" : "inactive"}>
          {editing === item.id ? <CategoryForm category={item} onDone={() => { setEditing(undefined); resource.reload(); }} /> : <>
            <div className="category-head">
              <div><h3>{item.name} {!item.active && <span className="neutral-tag">موقوفة</span>}</h3>
                <p>{item.description || "—"} · <span dir="ltr">{item.id}</span></p></div>
              <div className="category-counts">
                <Link className="text-link" href={`/documents?category=${item.id}`}>{number(item.confirmed)} معتمد · {number(item.suggested)} مقترح<Icon name="arrow" /></Link>
                {admin && <button className="button secondary compact" onClick={() => setEditing(item.id)}><Icon name="edit" />تعديل</button>}
              </div>
            </div>
            <ul className="keyword-list">{item.keywords.map(word => <li key={word} dir="auto">{word}</li>)}</ul>
            <small className="muted">آخر تعديل {date(item.updated_at)} · أنشأها {actors(item.created_by === "system" ? "system:classifier" : item.created_by)}</small>
          </>}
        </li>)}</ul>}
    </section>
  </>;
}

function CategoryForm({ category, onDone }: { category?: Category; onDone: () => void }) {
  const [id, setId] = useState(category?.id ?? ""), [name, setName] = useState(category?.name ?? "");
  const [description, setDescription] = useState(category?.description ?? "");
  const [keywords, setKeywords] = useState((category?.keywords ?? []).join("، "));
  const [active, setActive] = useState(category?.active ?? true);
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      if (category) await patch(`/categories/${category.id}`, { name, description, keywords: split(keywords), active });
      else await post("/categories", { id, name, description, keywords: split(keywords) });
      onDone();
    } catch (failure) { setError(failure instanceof Error ? failure.message : "تعذر حفظ الفئة."); }
    finally { setBusy(false); }
  }
  return <form className="review-form category-form" onSubmit={submit}>
    <h3>{category ? `تعديل «${category.name}»` : "فئة جديدة"}</h3>
    {!category && <><label htmlFor="category-id">المعرّف (أحرف إنجليزية صغيرة)</label>
      <input id="category-id" dir="ltr" value={id} onChange={e => setId(e.target.value)} required placeholder="memo" /></>}
    <label htmlFor="category-name">الاسم</label>
    <input id="category-name" value={name} onChange={e => setName(e.target.value)} required />
    <label htmlFor="category-description">الوصف</label>
    <input id="category-description" value={description} onChange={e => setDescription(e.target.value)} />
    <label htmlFor="category-keywords">الكلمات المفتاحية (افصل بينها بفاصلة)</label>
    <textarea id="category-keywords" dir="auto" rows={3} value={keywords} onChange={e => setKeywords(e.target.value)} required />
    <p className="muted small-note">تُطابق الكلمة كاملة مع حروف السوابق (و، ف، ب، ك، ل، ال)، ويتجاهل المطابقة اختلاف الهمزات والتشكيل. تغيير الكلمات يُعيد اقتراح التصنيف للمستندات عند إعادة الاقتراح.</p>
    {category && <label className="toggle"><input type="checkbox" checked={active} onChange={e => setActive(e.target.checked)} />فئة مفعّلة</label>}
    {error && <Failure message={error} />}
    <div className="form-actions">
      <button className="button primary compact" type="submit" disabled={busy}>حفظ</button>
      <button className="button secondary compact" type="button" onClick={onDone} disabled={busy}>إلغاء</button>
    </div>
  </form>;
}
