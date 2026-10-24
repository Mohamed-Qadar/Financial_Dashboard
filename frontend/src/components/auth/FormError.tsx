"use client";

import { Alert } from "@/components/ui/Alert";
import { ApiError } from "@/lib/api/errors";
import { errorMessage } from "@/lib/api/messages";
import { useI18n } from "@/lib/i18n/LocaleProvider";

/**
 * The error of a failed request, in the UI language. The request ID is shown only for
 * server-side failures, where support needs it; never any token or cookie value.
 */
export function FormError({ error }: { error: unknown }) {
  const { t } = useI18n();
  if (error === null || error === undefined) return null;
  const reference =
    error instanceof ApiError && (error.status >= 500 || error.status === 0)
      ? error.requestId
      : undefined;
  return (
    <Alert tone="danger" reference={reference} referenceLabel={t.common.reference}>
      {errorMessage(error, t)}
    </Alert>
  );
}
