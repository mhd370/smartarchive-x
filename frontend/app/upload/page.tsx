"use client";
import { useEffect, useRef, useState } from "react";
import type { DragEvent, FormEvent } from "react";
import Link from "next/link";
import { upload, type DocumentRecord, type Health } from "@/lib/api";
import { useApi } from "@/lib/use-api";
import { bytes } from "@/lib/format";
import { Icon } from "@/components/icons";
import { Failure, FileSymbol, Loading, StatusBadge } from "@/components/ui";

export default function UploadPage() {
  const health = useApi<Health>("/health");
  const [file, setFile] = useState<File>(), [error, setError] = useState("");
  const [busy, setBusy] = useState(false), [progress, setProgress] = useState(0);
  const [drag, setDrag] = useState(false), [saved, setSaved] = useState<DocumentRecord>();
  const input = useRef<HTMLInputElement>(null), request = useRef<AbortController | null>(null);
  useEffect(() => () => request.current?.abort(), []);
  function select(files: FileList | null) {
    if (busy || !files?.length) return;
    setError(""); setSaved(undefined); setFile(undefined);
    if (files.length !== 1) { setError("اختر ملفًا واحدًا في كل مرة."); return; }
    const next = files[0], extension = next.name.split(".").pop()?.toLowerCase() || "";
    if (!health.data?.supported_extensions.includes(extension)) { setError("اختر ملف PDF أو صورة PNG أو JPEG أو WebP أو TIFF."); return; }
    if (next.size === 0) { setError("الملف فارغ. اختر مستندًا يحتوي على بيانات."); return; }
    if (next.size > health.data.max_upload_bytes) { setError(`حجم الملف يتجاوز ${bytes(health.data.max_upload_bytes)}.`); return; }
    setFile(next);
  }
  function drop(event: DragEvent<HTMLDivElement>) { event.preventDefault(); setDrag(false); select(event.dataTransfer.files); }
  async function submit(event: FormEvent) {
    event.preventDefault(); if (!file || busy) return;
    setError(""); setBusy(true); setProgress(0);
    const controller = new AbortController(); request.current = controller;
    try { setSaved(await upload(file, setProgress, controller.signal)); }
    catch (failure) { setError(failure instanceof Error ? failure.message : "تعذر رفع المستند."); }
    finally { setBusy(false); request.current = null; }
  }
  function reset() { setSaved(undefined); setFile(undefined); setError(""); setProgress(0); if (input.current) input.current.value = ""; }
  return <><div className="page-heading"><div><span className="eyebrow">إضافة إلى الأرشيف</span><h1>رفع مستند جديد</h1><p>أضف ملفك واحفظ نسخة أصلية يمكنك الرجوع إليها.</p></div><Link href="/documents" className="text-link">العودة إلى المستندات<Icon name="arrow" /></Link></div><div className="upload-layout"><section className="panel upload-panel">
    {health.loading ? <Loading label="جار التحقق من إعدادات الرفع…" /> : health.error ? <Failure message={health.error} retry={health.reload} /> : saved ? <div className="upload-success" role="status"><span className="success-icon"><Icon name="check" /></span><h2>تم حفظ المستند</h2><p dir="auto">{saved.filename}</p><StatusBadge status={saved.status} /><p className="muted">{saved.status === "queued" ? "حُفظ الأصل كما أرسلته، وبدأت المعالجة الآلية: فحص جودة كل صفحة ثم استخراج النص." : "حُفظ الأصل كما أرسلته. محرك OCR غير مهيأ على الخادم، لذلك لم تبدأ المعالجة."}</p><div className="button-row"><Link href={`/documents/${saved.id}`} className="button primary">عرض المستند<Icon name="arrow" /></Link><button className="button secondary" onClick={reset}>رفع مستند آخر</button></div></div> : <form onSubmit={submit}><div className={`drop-area ${drag ? "dragging" : ""} ${busy ? "busy" : ""}`} onDragOver={event => { event.preventDefault(); if (!busy) setDrag(true); }} onDragLeave={() => setDrag(false)} onDrop={drop}><input id="document-file" ref={input} type="file" className="sr-only" accept=".pdf,.png,.jpg,.jpeg,.webp,.tif,.tiff" disabled={busy} onChange={event => select(event.target.files)} /><label htmlFor="document-file"><span className="upload-icon"><Icon name="upload" /></span><h2>اسحب مستندك وأفلته هنا</h2><p>أو اختر ملفًا من جهازك</p><span className="button secondary">اختيار ملف</span><small>PDF · PNG · JPEG · WebP · TIFF<br />حتى {bytes(health.data!.max_upload_bytes)} للملف الواحد</small></label></div>{file && <div className="selected-file"><FileSymbol mime={file.type} /><div><strong dir="auto">{file.name}</strong><small>{bytes(file.size)}</small></div><button type="button" className="icon-link" disabled={busy} aria-label="إزالة الملف المختار" onClick={reset}><Icon name="close" /></button></div>}{error && <Failure message={error} />}{busy && <div className="upload-progress" role="status"><div><span>{progress === 100 ? "جار التحقق من الملف وحفظه…" : "جار إرسال المستند…"}</span><b dir="ltr">{progress}%</b></div><div className="progress-track" role="progressbar" aria-label="تقدم رفع المستند" aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100}><span style={{ width: `${progress}%` }} /></div></div>}<div className="upload-submit"><span><Icon name="shield" />لن يُعدّل الملف الأصلي</span><button type="submit" className="button primary" disabled={!file || busy}><Icon name="upload" />{busy ? "جار الحفظ…" : "رفع وحفظ المستند"}</button></div></form>}
    </section><aside className="upload-guidance"><section className="panel"><span className="eyebrow">كيف يعمل الرفع؟</span><h2>من جهازك إلى الأرشيف</h2><ol className="steps"><li><b>١</b><div><strong>اختر المستند</strong><p>ملف PDF أو صورة واضحة، ضمن الحجم المسموح.</p></div></li><li><b>٢</b><div><strong>تحقق وحفظ</strong><p>نتحقق من نوع الملف، ونحفظ الأصل مع بصمته الرقمية.</p></div></li><li><b>٣</b><div><strong>فحص واستخراج</strong><p>تُقاس جودة كل صفحة ويُستخرج النص مع موقعه ودرجة الثقة.</p></div></li><li><b>٤</b><div><strong>استعرض وتتبع</strong><p>افتح المعاينة والنص المستخرج وسجل الأحداث.</p></div></li></ol></section><div className="info-note"><Icon name="clock" /><p>{health.data?.ocr_configured ? "بعد الحفظ تبدأ المعالجة تلقائيًا: فحص جودة كل صفحة، تصحيح الاتجاه والميل، ثم استخراج النص مع موقعه ودرجة ثقته. التصنيف والبحث الذكي في المراحل التالية." : "محرك OCR غير مهيأ على الخادم؛ ستُحفظ المستندات وتُعرض دون استخراج نص."}</p></div></aside></div></>;
}
