import { StatusPanel } from "@/components/StatusPanel";
import { getSystemStatus } from "@/lib/health";

// Status must be checked on every request, never prerendered at build time.
export const dynamic = "force-dynamic";

export default async function HomePage() {
  const status = await getSystemStatus(
    process.env.BACKEND_INTERNAL_URL ?? "http://localhost:8000",
  );

  return (
    <main className="container">
      <h1>Somali ERP</h1>
      <p className="muted">Development environment</p>
      <StatusPanel status={status} />
    </main>
  );
}
