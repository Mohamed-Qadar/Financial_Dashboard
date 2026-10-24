import type { ReactNode } from "react";

import { Icon, type IconName } from "./Icon";

type Tone = "info" | "success" | "warning" | "danger";

const ICONS: Record<Tone, IconName> = {
  info: "info",
  success: "check",
  warning: "alert",
  danger: "alert",
};

/**
 * Inline message. Errors use role="alert" (announced immediately); other tones use
 * role="status". `reference` shows the request ID so users can quote it to support.
 */
export function Alert({
  tone = "info",
  title,
  children,
  reference,
  referenceLabel,
}: {
  tone?: Tone;
  title?: string;
  children?: ReactNode;
  reference?: string;
  referenceLabel?: string;
}) {
  return (
    <div className="ui-alert" data-tone={tone} role={tone === "danger" ? "alert" : "status"}>
      <Icon name={ICONS[tone]} size={18} />
      <div className="ui-alert-body">
        {title ? <p className="ui-alert-title">{title}</p> : null}
        {children ? <div>{children}</div> : null}
        {reference ? (
          <p className="ui-alert-reference">
            {referenceLabel ?? "Reference"}: <code>{reference}</code>
          </p>
        ) : null}
      </div>
    </div>
  );
}
