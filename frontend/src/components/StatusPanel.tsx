import type { ApiState, DatabaseState, SystemStatus } from "@/lib/health";

type State = ApiState | DatabaseState;

const LABELS: Record<State, string> = {
  ok: "Operational",
  error: "Error",
  unavailable: "Unavailable",
  unreachable: "Unreachable",
  unknown: "Unknown",
};

export function StatusPanel({ status }: { status: SystemStatus }) {
  const rows: { name: string; state: State }[] = [
    { name: "API", state: status.api },
    { name: "Database", state: status.database },
  ];

  return (
    <section className="status-panel" aria-labelledby="system-status-heading">
      <h2 id="system-status-heading">System status</h2>
      <ul>
        {rows.map((row) => (
          <li key={row.name}>
            <span>{row.name}</span>
            <span className={`badge ${row.state === "ok" ? "badge-ok" : "badge-problem"}`}>
              {LABELS[row.state]}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
