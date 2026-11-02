import { Suspense } from "react";
import { Loading } from "@/components/ui";
import SearchResults from "./results";
export default function Page() { return <Suspense fallback={<Loading />}><SearchResults /></Suspense>; }
