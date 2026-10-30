import { Suspense } from "react";
import { Loading } from "@/components/ui";
import Documents from "./table";
export default function Page() { return <Suspense fallback={<Loading />}><Documents /></Suspense>; }
