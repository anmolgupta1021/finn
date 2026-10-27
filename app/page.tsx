import { getDigest } from "@/lib/data";
import { BriefingPage } from "@/components/briefing-page";

// Read pipeline outputs on each request; never pre-render a stale snapshot.
export const dynamic = "force-dynamic";

export default function Home() {
  return <BriefingPage digest={getDigest()} />;
}
