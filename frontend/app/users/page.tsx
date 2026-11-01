"use client";
import { useState } from "react";
import type { FormEvent } from "react";
import { patch, post, type Role, type User } from "@/lib/api";
import { roleNames, useAuth } from "@/lib/auth";
import { useApi } from "@/lib/use-api";
import { date } from "@/lib/format";
import { Icon } from "@/components/icons";
import { Failure, Loading } from "@/components/ui";

const roles: Role[] = ["admin", "archivist", "reviewer", "viewer"];
const roleHelp: Record<Role, string> = {
  admin: "كل الصلاحيات وإدارة المستخدمين",
  archivist: "رفع المستندات وتشغيل المعالجة",
  reviewer: "مراجعة النتائج والتصحيح",
  viewer: "اطلاع وتنزيل فقط",
};

export default function UsersPage() {
  const { can, user: me } = useAuth();
  const users = useApi<{ items: User[] }>(can("users.manage") ? "/users" : null);
  const [form, setForm] = useState({ username: "", display_name: "", role: "archivist" as Role, password: "" });
  const [error, setError] = useState(""), [notice, setNotice] = useState(""), [busy, setBusy] = useState(false);
  const [resetFor, setResetFor] = useState<string>(), [newPassword, setNewPassword] = useState("");

  if (!can("users.manage")) return <Failure message="هذه الصفحة متاحة لمدير النظام فقط." />;

  async function run(action: () => Promise<unknown>, done: string) {
    setError(""); setNotice(""); setBusy(true);
    try { await action(); setNotice(done); users.reload(); return true; }
    catch (failure) { setError(failure instanceof Error ? failure.message : "تعذر تنفيذ الإجراء."); return false; }
    finally { setBusy(false); }
  }
  async function create(event: FormEvent) {
    event.preventDefault();
    if (await run(() => post("/users", form), `أُنشئ حساب ${form.username}.`))
      setForm({ username: "", display_name: "", role: "archivist", password: "" });
  }
  async function resetPassword(event: FormEvent, user: User) {
    event.preventDefault();
    if (await run(() => patch(`/users/${user.id}`, { password: newPassword }), `حُدّثت كلمة مرور ${user.username} وأُنهيت جلساته.`)) {
      setResetFor(undefined); setNewPassword("");
    }
  }

  return <>
    <div className="page-heading"><div><span className="eyebrow">الإدارة</span><h1>المستخدمون والصلاحيات</h1><p>كل إجراء في الأرشيف يُسجَّل باسم المستخدم الذي نفّذه.</p></div></div>
    {error && <Failure message={error} />}
    {notice && <div className="notice-state" role="status"><Icon name="check" />{notice}</div>}
    <div className="users-layout">
      <section className="panel">
        <div className="section-heading"><div><h2>الحسابات</h2><p>تغيير الدور أو تعطيل الحساب يُنهي جلساته الحالية.</p></div></div>
        {users.loading ? <Loading /> : users.error ? <Failure message={users.error} retry={users.reload} /> :
          <div className="table-scroll"><table><thead><tr><th>المستخدم</th><th>الدور</th><th>الحالة</th><th>أُنشئ</th><th>إجراءات</th></tr></thead><tbody>
            {users.data?.items.map(user => <tr key={user.id}>
              <td><strong dir="auto">{user.display_name}</strong><small className="block muted" dir="ltr">{user.username}</small></td>
              <td><select aria-label={`دور ${user.username}`} value={user.role} disabled={busy}
                onChange={event => run(() => patch(`/users/${user.id}`, { role: event.target.value }), `تغيّر دور ${user.username}.`)}>
                {roles.map(role => <option key={role} value={role}>{roleNames[role]}</option>)}</select></td>
              <td><span className={`status ${user.active ? "status-ready" : "status-failed"}`}><span />{user.active ? "نشط" : "معطّل"}</span></td>
              <td className="muted nowrap">{date(user.created_at)}</td>
              <td className="row-actions">
                <button className="button secondary compact" disabled={busy || user.id === me?.id}
                  onClick={() => run(() => patch(`/users/${user.id}`, { active: !user.active }), user.active ? `عُطّل حساب ${user.username}.` : `فُعّل حساب ${user.username}.`)}>
                  {user.active ? "تعطيل" : "تفعيل"}</button>
                <button className="button secondary compact" disabled={busy} onClick={() => { setResetFor(resetFor === user.id ? undefined : user.id); setNewPassword(""); }}>كلمة المرور</button>
                {resetFor === user.id && <form className="inline-form" onSubmit={event => resetPassword(event, user)}>
                  <input dir="ltr" type="password" aria-label={`كلمة مرور جديدة لـ ${user.username}`} placeholder="8 أحرف على الأقل" minLength={8} required value={newPassword} onChange={e => setNewPassword(e.target.value)} />
                  <button className="button primary compact" disabled={busy}>حفظ</button></form>}
              </td>
            </tr>)}
          </tbody></table></div>}
      </section>
      <section className="panel">
        <h2>إضافة مستخدم</h2>
        <form className="stack-form" onSubmit={create}>
          <label className="field"><span>الاسم الظاهر</span><input value={form.display_name} required maxLength={80} onChange={e => setForm({ ...form, display_name: e.target.value })} /></label>
          <label className="field"><span>اسم المستخدم</span><input dir="ltr" value={form.username} required minLength={3} maxLength={40} pattern="[A-Za-z0-9_.\-]+" onChange={e => setForm({ ...form, username: e.target.value })} /></label>
          <label className="field"><span>الدور</span><select value={form.role} onChange={e => setForm({ ...form, role: e.target.value as Role })}>{roles.map(role => <option key={role} value={role}>{roleNames[role]} — {roleHelp[role]}</option>)}</select></label>
          <label className="field"><span>كلمة المرور المؤقتة</span><input dir="ltr" type="password" value={form.password} required minLength={8} autoComplete="new-password" onChange={e => setForm({ ...form, password: e.target.value })} /></label>
          <button className="button primary" disabled={busy}><Icon name="user" />إنشاء الحساب</button>
        </form>
      </section>
    </div>
  </>;
}
