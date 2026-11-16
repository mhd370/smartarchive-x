"use client";
import { Suspense, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { get, post, type AuthStatus, type User } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Icon } from "@/components/icons";
import { Failure, Loading } from "@/components/ui";

export default function LoginPage() {
  return <Suspense fallback={<Loading />}><LoginForm /></Suspense>;
}

function LoginForm() {
  const router = useRouter(), params = useSearchParams();
  const { signedIn } = useAuth();
  const [status, setStatus] = useState<AuthStatus>(), [loadError, setLoadError] = useState("");
  const [username, setUsername] = useState(""), [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState(""), [confirm, setConfirm] = useState("");
  const [setupToken, setSetupToken] = useState("");
  const [error, setError] = useState(""), [busy, setBusy] = useState(false);
  const next = params.get("next");
  const target = next && next.startsWith("/") && !next.startsWith("//") && next !== "/login" ? next : "/";

  useEffect(() => {
    get<AuthStatus>("/auth/status").then(value => {
      if (value.authenticated) router.replace(target); else setStatus(value);
    }).catch((failure: Error) => setLoadError(failure.message));
  }, [router, target]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setError("");
    if (status?.setup_required && password !== confirm) { setError("كلمتا المرور غير متطابقتين."); return; }
    setBusy(true);
    try {
      const user = status?.setup_required
        ? await post<User>("/auth/setup", { username, password, display_name: displayName,
          ...(status?.setup_token_required ? { setup_token: setupToken } : {}) })
        : await post<User>("/auth/login", { username, password });
      signedIn(user);
      router.replace(target);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "تعذر تسجيل الدخول.");
      setBusy(false);
    }
  }

  const setup = status?.setup_required;
  return <div className="auth-card panel">
    <div className="auth-brand"><span className="brand-mark"><Icon name="archive" /></span><div><b dir="ltr">SmartArchive<span>—X</span></b><small>الأرشيف المؤسسي العربي</small></div></div>
    {loadError ? <Failure message={loadError} retry={() => window.location.reload()} /> : !status ? <Loading label="جار التحقق من حالة النظام…" /> : <form onSubmit={submit}>
      <h1>{setup ? "إعداد حساب المدير" : "تسجيل الدخول"}</h1>
      <p>{setup ? "هذا أول تشغيل للنظام. أنشئ حساب مدير النظام لإدارة المستخدمين والصلاحيات." : "سجّل الدخول للوصول إلى مساحة الأرشيف."}</p>
      {setup && status?.setup_token_required && <label className="field"><span>رمز الإعداد</span><input dir="ltr" type="password" value={setupToken} onChange={e => setSetupToken(e.target.value)} required autoComplete="off" /></label>}
      {setup && <label className="field"><span>الاسم الظاهر</span><input value={displayName} onChange={e => setDisplayName(e.target.value)} required maxLength={80} autoComplete="name" /></label>}
      <label className="field"><span>اسم المستخدم</span><input dir="ltr" value={username} onChange={e => setUsername(e.target.value)} required minLength={3} maxLength={40} autoComplete="username" /></label>
      <label className="field"><span>كلمة المرور</span><input dir="ltr" type="password" value={password} onChange={e => setPassword(e.target.value)} required minLength={setup ? 8 : 1} autoComplete={setup ? "new-password" : "current-password"} /></label>
      {setup && <label className="field"><span>تأكيد كلمة المرور</span><input dir="ltr" type="password" value={confirm} onChange={e => setConfirm(e.target.value)} required minLength={8} autoComplete="new-password" /></label>}
      {error && <Failure message={error} />}
      <button className="button primary auth-submit" type="submit" disabled={busy}><Icon name={setup ? "shield" : "lock"} />{busy ? "جار التحقق…" : setup ? "إنشاء الحساب والدخول" : "دخول"}</button>
      <small className="auth-note"><Icon name="shield" />الجلسة محفوظة في الخادم، وتُسجَّل محاولات الدخول.</small>
    </form>}
  </div>;
}
