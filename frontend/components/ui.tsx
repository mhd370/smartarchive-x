import Link from "next/link";
import type { DocumentRecord, Status } from "@/lib/api";
import { bytes, date, statuses } from "@/lib/format";
import { Icon } from "./icons";

export function StatusBadge({ status }: { status: Status }) {
  return <span className={`status status-${status}`}><span />{statuses[status]}</span>;
}
export function FileSymbol({ mime }: { mime: string }) {
  const pdf = mime === "application/pdf";
  return <span className={`file-symbol ${pdf ? "pdf" : "image"}`}><Icon name={pdf ? "file" : "image"} /><small>{pdf ? "PDF" : "IMG"}</small></span>;
}
export function Loading({ label = "جار تحميل البيانات…" }: { label?: string }) {
  return <div role="status" className="loading-state"><span className="spinner" />{label}</div>;
}
export function Failure({ message, retry }: { message: string; retry?: () => void }) {
  return <div role="alert" className="error-state"><p>{message}</p>{retry && <button className="button secondary" onClick={retry}><Icon name="refresh" />إعادة المحاولة</button>}</div>;
}
export function Empty({ filtered = false }: { filtered?: boolean }) {
  return <div className="empty-state"><div className="empty-icon"><Icon name={filtered ? "search" : "folder"} /></div><h3>{filtered ? "لا توجد نتائج مطابقة" : "أرشيفك جاهز لأول مستند"}</h3><p>{filtered ? "جرّب اسمًا مختلفًا أو عدّل خيارات التصفية." : "ارفع مستندًا لبدء تنظيمه وحفظ أصله في مساحة الأرشيف."}</p><Link className="button primary" href={filtered ? "/documents" : "/upload"}>{filtered ? "عرض جميع المستندات" : "رفع أول مستند"}<Icon name={filtered ? "arrow" : "upload"} /></Link></div>;
}
export function DocumentTable({ documents }: { documents: DocumentRecord[] }) {
  return <div className="table-scroll"><table><thead><tr><th>المستند</th><th>الصفحات</th><th>الحجم</th><th>الحالة</th><th>تاريخ الإضافة</th><th><span className="sr-only">التفاصيل</span></th></tr></thead><tbody>{documents.map(doc => <tr key={doc.id}><td><Link href={`/documents/${doc.id}`} className="document-name"><FileSymbol mime={doc.mime_type} /><span><strong dir="auto">{doc.filename}</strong><small dir="ltr">{doc.mime_type}</small></span></Link></td><td>{doc.page_count}</td><td className="nowrap">{bytes(doc.size_bytes)}</td><td><StatusBadge status={doc.status} /></td><td className="muted nowrap">{date(doc.created_at)}</td><td><Link href={`/documents/${doc.id}`} className="icon-link" aria-label={`تفاصيل ${doc.filename}`}><Icon name="arrow" /></Link></td></tr>)}</tbody></table></div>;
}
