"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import type { ReactNode, FormEvent } from "react";
import { useApi } from "@/lib/use-api";
import type { Health, Permission } from "@/lib/api";
import { AuthProvider, PUBLIC_PATHS, roleNames, useAuth } from "@/lib/auth";
import { Icon, type IconName } from "./icons";
import { Loading } from "./ui";

const navigation: { href: string; label: string; icon: IconName; permission: Permission }[] = [
  { href: "/", label: "لوحة التحكم", icon: "dashboard", permission: "documents.read" },
  { href: "/documents", label: "المستندات", icon: "folder", permission: "documents.read" },
  { href: "/search", label: "البحث في النصوص", icon: "search", permission: "documents.read" },
  { href: "/review", label: "المراجعة", icon: "review", permission: "review.write" },
  { href: "/categories", label: "التصنيفات", icon: "tag", permission: "documents.read" },
  { href: "/upload", label: "رفع مستند", icon: "upload", permission: "documents.upload" },
  { href: "/users", label: "المستخدمون", icon: "users", permission: "users.manage" },
];
const titles: Record<string, string> = { "/": "نظرة عامة", "/upload": "رفع مستند", "/documents": "المستندات", "/users": "المستخدمون",
  "/search": "البحث في النصوص", "/review": "المراجعة", "/categories": "التصنيفات" };

export function Shell({ children }: { children: ReactNode }) {
  return <AuthProvider><Frame>{children}</Frame></AuthProvider>;
}

function Frame({ children }: { children: ReactNode }) {
  const path = usePathname(), router = useRouter();
  const { user, checking, can, signOut } = useAuth();
  const [open, setOpen] = useState(false), [search, setSearch] = useState("");
  const health = useApi<Health>("/health");
  if (PUBLIC_PATHS.includes(path)) return <main id="main-content" className="auth-page">{children}</main>;
  if (checking || !user) return <main id="main-content" className="auth-page"><Loading label="جار التحقق من الجلسة…" /></main>;
  function submit(event: FormEvent) { event.preventDefault(); if (search.trim()) router.push(`/search?q=${encodeURIComponent(search.trim())}`); }
  const items = navigation.filter(item => can(item.permission));
  const active = (href: string) => href === "/" ? path === "/" : path.startsWith(href);
  return <div className="app-frame">
    {open && <button aria-label="إغلاق القائمة" className="mobile-backdrop" onClick={() => setOpen(false)} />}
    <aside className={`sidebar ${open ? "sidebar-open" : ""}`} aria-label="التنقل الرئيسي">
      <Link href="/" className="brand" onClick={() => setOpen(false)}><span className="brand-mark"><Icon name="archive" /></span><span><b dir="ltr">SmartArchive<span>—X</span></b><small>الأرشيف المؤسسي العربي</small></span></Link>
      <div className="workspace-label">مساحة العمل المحلية</div>
      <nav>{items.map(item => <Link key={item.href} href={item.href} onClick={() => setOpen(false)} className={`nav-link ${active(item.href) ? "active" : ""}`} aria-current={active(item.href) ? "page" : undefined}><Icon name={item.icon} />{item.label}</Link>)}</nav>
      <div className="sidebar-note"><Icon name="shield" /><strong>الأصل محفوظ، والأثر واضح</strong><p>كل إجراء يُسجَّل باسم من قام به ووقته.</p></div>
      <div className="user-card"><span className="user-avatar"><Icon name="user" /></span><div><strong dir="auto">{user.display_name}</strong><small>{roleNames[user.role]} · <span dir="ltr">{user.username}</span></small></div><button onClick={signOut} aria-label="تسجيل الخروج" title="تسجيل الخروج"><Icon name="logout" /></button></div>
      <div className={`connection ${health.error ? "offline" : ""}`}><span className={health.data ? "connected-dot" : "pending-dot"} /><div>{health.data ? "متصل بخدمة الأرشيف" : health.error ? "الخدمة غير متاحة" : "جار التحقق من الاتصال…"}<small>{health.data ? (health.data.ocr_configured ? `OCR: ${health.data.ocr_engine} · ${health.data.ocr_languages}` : "OCR غير مهيأ على الخادم") : "تحقق من تشغيل خادم API"}</small></div>{health.error && <button onClick={health.reload} aria-label="إعادة فحص الاتصال"><Icon name="refresh" /></button>}</div>
    </aside>
    <div className="main-column"><header className="topbar"><div className="topbar-title"><button className="mobile-menu icon-link" aria-label="فتح القائمة" aria-expanded={open} onClick={() => setOpen(!open)}><Icon name="menu" /></button><span>مساحة الأرشيف <span className="breadcrumb-slash">/</span> <strong>{titles[path] || "تفاصيل المستند"}</strong></span></div><form role="search" className="global-search" onSubmit={submit}><Icon name="search" /><input aria-label="بحث في نصوص المستندات وأسمائها" placeholder="ابحث في نصوص المستندات…" value={search} onChange={e => setSearch(e.target.value)} /></form>{can("documents.upload") && <Link className="button primary compact" href="/upload"><Icon name="upload" /><span>رفع مستند</span></Link>}</header><main id="main-content" className="page-content">{children}</main><footer className="app-footer"><span dir="ltr">SmartArchive-X</span><span>أرشفة عربية · أصول محفوظة · نتائج قابلة للتتبّع</span></footer></div>
  </div>;
}
