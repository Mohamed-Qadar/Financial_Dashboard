"use client";

import { Button, ButtonLink } from "@/components/ui/Button";
import { useI18n } from "@/lib/i18n/LocaleProvider";

/**
 * Unexpected rendering errors (Next.js 16 error boundary: `error` + `retry`). The error
 * itself is not shown: its message could contain internal details. Next.js logs it.
 */
export default function ErrorPage({ retry }: { error: unknown; retry: () => void }) {
  const { t } = useI18n();
  return (
    <main id="main-content" className="standalone-page">
      <div className="ui-card" role="alert">
        <h1>{t.pages.errorTitle}</h1>
        <p>{t.pages.errorBody}</p>
        <div className="ui-button-row">
          <Button onClick={() => retry()}>{t.common.retry}</Button>
          <ButtonLink href="/">{t.pages.goHome}</ButtonLink>
        </div>
      </div>
    </main>
  );
}
