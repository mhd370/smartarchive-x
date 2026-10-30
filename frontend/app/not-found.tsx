import Link from "next/link";
export default function NotFound() { return <div className="empty-state"><h1>الصفحة غير موجودة</h1><p>تحقق من الرابط أو عد إلى مساحة الأرشيف.</p><Link href="/" className="button primary">لوحة التحكم</Link></div>; }
