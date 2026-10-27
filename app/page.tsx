import { getDigest } from "@/lib/data";
import { BriefingPage } from "@/components/briefing-page";

export default function Home() {
  const digest = getDigest();

  if (!digest) {
    return (
      <div className="flex items-center justify-center min-h-screen p-4">
        <div className="text-center">
          <h1 className="text-lg font-bold mb-2">FINN</h1>
          <p className="text-sm text-finn-muted">
            No digest data available. Run the pipeline first.
          </p>
        </div>
      </div>
    );
  }

  return <BriefingPage digest={digest} />;
}
