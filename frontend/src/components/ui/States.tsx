"use client";

import type { ReactNode } from "react";

import { ApiError } from "@/lib/api/errors";
import { errorMessage } from "@/lib/api/messages";
import { useI18n } from "@/lib/i18n/LocaleProvider";

import { Button } from "./Button";
import { Icon, type IconName } from "./Icon";
import { Spinner } from "./Spinner";

export function EmptyState({
  icon = "info",
  title,
  children,
  actions,
}: {
  icon?: IconName;
  title: string;
  children?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="ui-empty">
      <span className="ui-empty-icon">
        <Icon name={icon} size={20} />
      </span>
      <p className="ui-empty-title">{title}</p>
      {children ? <div className="ui-empty-body">{children}</div> : null}
      {actions ? <div className="ui-empty-actions">{actions}</div> : null}
    </div>
  );
}

/** A failed load with the localized reason, a retry button and (for server faults) the request ID. */
export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const { t } = useI18n();
  const reference =
    error instanceof ApiError && (error.status >= 500 || error.status === 0) ? error.requestId : undefined;
  return (
    <div className="ui-empty" role="alert">
      <span className="ui-empty-icon" data-tone="danger">
        <Icon name="alert" size={20} />
      </span>
      <p className="ui-empty-title">{t.pages.errorTitle}</p>
      <div className="ui-empty-body">
        <p>{errorMessage(error, t)}</p>
        {reference ? (
          <p className="ui-alert-reference">
            {t.common.reference}: <code>{reference}</code>
          </p>
        ) : null}
      </div>
      {onRetry ? (
        <div className="ui-empty-actions">
          <Button variant="secondary" onClick={onRetry}>
            {t.common.retry}
          </Button>
        </div>
      ) : null}
    </div>
  );
}

export function PageLoading() {
  const { t } = useI18n();
  return (
    <div className="ui-page-loading">
      <Spinner label={t.common.loading} />
    </div>
  );
}

export function Skeleton({ width }: { width?: "short" | "medium" }) {
  return <span className="ui-skeleton" data-width={width} aria-hidden="true" />;
}

/**
 * Page title block: optional eyebrow (context), leading visual, description, facts shown as
 * chips (`meta`, real values only) and actions.
 */
export function PageHeader({
  title,
  eyebrow,
  leading,
  description,
  meta,
  actions,
}: {
  title: string;
  eyebrow?: string;
  leading?: ReactNode;
  description?: ReactNode;
  meta?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="ui-page-header">
      <div className="ui-page-header-main">
        {leading ? <div className="ui-page-header-leading">{leading}</div> : null}
        <div className="ui-page-header-text">
          {eyebrow ? <p className="ui-eyebrow">{eyebrow}</p> : null}
          <h1>{title}</h1>
          {description ? <p className="ui-page-header-description">{description}</p> : null}
          {meta ? <div className="ui-chips">{meta}</div> : null}
        </div>
      </div>
      {actions ? <div className="ui-button-row">{actions}</div> : null}
    </header>
  );
}

/** A small labelled fact ("USD", "TEST1") for page headers. */
export function Chip({ icon, children }: { icon?: IconName; children: ReactNode }) {
  return (
    <span className="ui-chip">
      {icon ? <Icon name={icon} size={14} /> : null}
      {children}
    </span>
  );
}
