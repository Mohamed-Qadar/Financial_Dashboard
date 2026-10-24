import { type ReactNode, useId } from "react";

/** A titled surface. The title labels the section for screen readers. */
export function Card({
  title,
  actions,
  children,
}: {
  title?: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  const titleId = useId();
  return (
    <section className="ui-card" aria-labelledby={title ? titleId : undefined}>
      {title || actions ? (
        <header className="ui-card-header">
          {title ? (
            <h2 id={titleId} className="ui-card-title">
              {title}
            </h2>
          ) : null}
          {actions ? <div className="ui-card-actions">{actions}</div> : null}
        </header>
      ) : null}
      {children}
    </section>
  );
}
