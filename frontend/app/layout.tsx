import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Shell } from "@/components/shell";
import "./globals.css";

export const metadata: Metadata = { title: { default: "SmartArchive-X | الأرشيف المؤسسي", template: "%s | SmartArchive-X" }, description: "مساحة محلية لحفظ المستندات العربية وأصولها وتتبعها." };
export default function RootLayout({ children }: { children: ReactNode }) {
  return <html lang="ar" dir="rtl"><body><a className="skip-link" href="#main-content">انتقل إلى المحتوى</a><Shell>{children}</Shell></body></html>;
}
