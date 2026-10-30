"use client";
import { Failure } from "@/components/ui";
export default function Error({ reset }: { reset: () => void }) { return <Failure message="تعذر عرض الصفحة. أعد المحاولة أو ارجع إلى المستندات." retry={reset} />; }
