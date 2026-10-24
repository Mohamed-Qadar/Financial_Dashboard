import type { ApiState, DatabaseState, SystemStatus } from "@/lib/health";
import type { Messages } from "@/lib/i18n";

type State = ApiState | DatabaseState;

/** API and database health. Works in server and client components (messages are a prop). */
export function StatusPanel({
  status,
  messages,
}: {
  status: SystemStatus;
  messages: Messages["status"];
}) {
  const rows: { name: string; state: State }[] = [
    { name: messages.api, state: status.api },
    { name: messages.database, state: status.database },
  ];

  return (
    <section className="ui-status" aria-labelledby="system-status-heading">
      <h2 id="system-status-heading" className="ui-card-title">
        {messages.title}
      </h2>
      <ul className="ui-status-list" role="list">
        {rows.map((row) => (
          <li key={row.name}>
            <span>{row.name}</span>
            <span className="ui-badge" data-tone={row.state === "ok" ? "success" : "danger"}>
              {messages.states[row.state]}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
