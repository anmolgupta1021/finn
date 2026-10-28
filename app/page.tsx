import { getDigest, getResearch } from "@/lib/data";
import { BriefingPage } from "@/components/briefing-page";

// Read pipeline outputs on each request; never pre-render a stale snapshot.
export const dynamic = "force-dynamic";

export default async function Home({
  searchParams,
}: {
  searchParams?: Promise<{ hours?: string; research?: string }>;
}) {
  const sp = searchParams ? await searchParams : {};
  const hours = sp?.hours ? Math.max(1, Number(sp.hours) || 24) : 24;
  const research = sp?.research ? getResearch(sp.research) : null;
  return (
    <BriefingPage
      digest={getDigest(hours)}
      initialHours={hours}
      initialResearch={research}
    />
  );
}
