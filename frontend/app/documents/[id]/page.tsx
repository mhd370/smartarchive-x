import Detail from "./detail";
export default async function Page({ params, searchParams }: {
  params: Promise<{ id: string }>; searchParams: Promise<{ page?: string; q?: string }> }) {
  const { id } = await params;
  const { page, q } = await searchParams;
  const first = Number(page);
  // From a search result: open on the page that matched and outline the lines holding the query's words.
  return <Detail id={id} initialPage={Number.isInteger(first) && first > 0 ? first : 1} query={(q || "").slice(0, 200)} />;
}
