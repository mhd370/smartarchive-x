"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import type { ReactNode, FormEvent } from "react";
import { useApi } from "@/lib/use-api";
import type { Health } from "@/lib/api";
import { Icon, type IconName } from "./icons";

const navigation: { href: string; label: string; icon: IconName }[] = [
  { href: "/", label: "لوحة التحكم", icon: "dashboard" },
  { href: "/documents", label: "المستندات", icon: "folder" },
  { href: "/upload", label: "رفع مستند", icon: "upload" },
];
export function Shell({ children }: { children: ReactNode }) {
  const path = usePathname(), router = useRouter();
  const [open, setOpen] = useState(false), [search, setSearch] = useState("");
  const health = useApi<Health>("/health");
  function submit(event: FormEvent) { event.preventDefault(); router.push(`/documents?q=${encodeURIComponent(search)}`); }
  return <div className="app-frame">
    {open && <button aria-label="إغلاق القائمة" className="mobile-backdrop" onClick={() => setOpen(false)} />}
    <aside className={`sidebar ${open ? "sidebar-open" : ""}`} aria-label="التنقل الرئيسي">
      <Link href="/" className="brand" onClick={() => setOpen(false)}><span className="brand-mark"><Icon name="archive" /></span><span><b dir="ltr">SmartArchive<span>—X</span></b><small>الأرشيف المؤسسي العربي</small></span></Link>
      <div className="workspace-label">مساحة العمل المحلية</div>
      <nav>{navigation.map(item => <Link key={item.href} href={item.href} onClick={() => setOpen(false)} className={`nav-link ${(item.href === "/" ? path === "/" : path.startsWith(item.href)) ? "active" : ""}`} aria-current={(item.href === "/" ? path === "/" : path.startsWith(item.href)) ? "page" : undefined}><Icon name={item.icon} />{item.label}</Link>)}</nav>
      <div className="sidebar-note"><Icon name="shield" /><strong>الأصل محفوظ، والأثر واضح</strong><p>احتفظ بالمستند الأصلي وتتبّع أحداثه من سجل النشاط.</p></div>
      <div className={`connection ${health.error ? "offline" : ""}`}><span className={health.data ? "connected-dot" : "pending-dot"} /><div>{health.data ? "متصل بخدمة الأرشيف" : health.error ? "الخدمة غير متاحة" : "جار التحقق من الاتصال…"}<small>{health.data ? "تخزين محلي · SQLite" : "تحقق من تشغيل خادم API"}</small></div>{health.error && <button onClick={health.reload} aria-label="إعادة فحص الاتصال"><Icon name="refresh" /></button>}</div>
    </aside>
    <div className="main-column"><header className="topbar"><div className="topbar-title"><button className="mobile-menu icon-link" aria-label="فتح القائمة" aria-expanded={open} onClick={() => setOpen(!open)}><Icon name="menu" /></button><span>مساحة الأرشيف <span className="breadcrumb-slash">/</span> <strong>{path === "/" ? "نظرة عامة" : path === "/upload" ? "رفع مستند" : path === "/documents" ? "المستندات" : "تفاصيل المستند"}</strong></span></div><form role="search" className="global-search" onSubmit={submit}><Icon name="search" /><input aria-label="بحث في أسماء المستندات" placeholder="ابحث عن مستند…" value={search} onChange={e => setSearch(e.target.value)} /></form><Link className="button primary compact" href="/upload"><Icon name="upload" /><span>رفع مستند</span></Link></header><main id="main-content" className="page-content">{children}</main><footer className="app-footer"><span dir="ltr">SmartArchive-X</span><span>أرشفة عربية · أصول محفوظة · نتائج قابلة للتتبّع</span></footer></div>
  </div>;
}
