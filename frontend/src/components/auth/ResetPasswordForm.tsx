"use client";

import Link from "next/link";
import { type FormEvent, useEffect, useRef, useState } from "react";

import { Alert } from "@/components/ui/Alert";
import { Button, ButtonLink } from "@/components/ui/Button";
import { PasswordField } from "@/components/ui/Field";
import { Spinner } from "@/components/ui/Spinner";
import { auth } from "@/lib/api/endpoints";
import { ApiError, isApiError } from "@/lib/api/errors";
import { useI18n } from "@/lib/i18n/LocaleProvider";

import { FormError } from "./FormError";

interface ResetLink {
  uid: string;
  token: string;
}

// Limits of the backend serializer (PasswordResetConfirmSerializer).
const MAX_UID = 64;
const MAX_TOKEN = 128;

/**
 * Reads uid/token from the e-mailed link (`/reset-password?uid=…&token=…`) once, then removes
 * them from the address bar and history, so the token does not linger in the URL. The
 * token is never displayed or logged. Referrer-Policy: no-referrer (next.config.ts) keeps it
 * out of outgoing requests.
 */
function takeLinkFromUrl(): ResetLink | null {
  const params = new URLSearchParams(window.location.search);
  const uid = params.get("uid");
  const token = params.get("token");
  if (window.location.search !== "") {
    window.history.replaceState(window.history.state, "", window.location.pathname);
  }
  if (!uid || !token || uid.length > MAX_UID || token.length > MAX_TOKEN) return null;
  return { uid, token };
}

export function ResetPasswordForm() {
  const { t } = useI18n();
  const captured = useRef<ResetLink | null | undefined>(undefined);
  const [link, setLink] = useState<ResetLink | null | undefined>(undefined);
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [localError, setLocalError] = useState<{ password?: string; confirmation?: string }>({});
  const [failure, setFailure] = useState<unknown>(null);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  useEffect(() => {
    // A ref, not state: React's development double-run of effects must not read the URL
    // again after it was cleared.
    if (captured.current === undefined) captured.current = takeLinkFromUrl();
    setLink(captured.current);
  }, []);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!link) return;
    const errors = {
      password: password === "" ? t.common.required : undefined,
      confirmation:
        confirmation === ""
          ? t.common.required
          : confirmation !== password
            ? t.auth.reset.mismatch
            : undefined,
    };
    setLocalError(errors);
    if (errors.password || errors.confirmation) return;

    setSubmitting(true);
    setFailure(null);
    try {
      await auth.confirmPasswordReset(link.uid, link.token, password);
      setDone(true);
    } catch (error) {
      const fields = error instanceof ApiError ? error.fieldErrors() : {};
      if (isApiError(error, "invalid_reset_link") || fields.uid || fields.token) {
        setLink(null);
      } else {
        setFailure(error);
      }
    } finally {
      setSubmitting(false);
    }
  }

  if (link === undefined) {
    return (
      <div className="auth-card">
        <Spinner label={t.common.loading} />
      </div>
    );
  }

  if (done) {
    return (
      <div className="auth-card">
        <h1>{t.auth.reset.doneTitle}</h1>
        <Alert tone="success">{t.auth.reset.doneBody}</Alert>
        <ButtonLink href="/login" variant="primary">
          {t.auth.login.submit}
        </ButtonLink>
      </div>
    );
  }

  if (link === null) {
    return (
      <div className="auth-card">
        <h1>{t.auth.reset.invalidTitle}</h1>
        <Alert tone="warning">{t.auth.reset.invalidBody}</Alert>
        <ButtonLink href="/forgot-password" variant="primary">
          {t.auth.reset.requestNew}
        </ButtonLink>
        <p className="auth-links">
          <Link href="/login">{t.auth.forgot.backToLogin}</Link>
        </p>
      </div>
    );
  }

  const fieldErrors = failure instanceof ApiError ? failure.fieldErrors() : {};
  return (
    <div className="auth-card">
      <h1>{t.auth.reset.title}</h1>
      <FormError error={failure} />
      <form className="ui-form" noValidate onSubmit={onSubmit}>
        <PasswordField
          label={t.auth.reset.newPassword}
          name="new_password"
          autoComplete="new-password"
          autoFocus
          required
          hint={t.auth.reset.hint}
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          error={localError.password ?? fieldErrors.new_password}
          showLabel={t.auth.login.showPassword}
          hideLabel={t.auth.login.hidePassword}
        />
        <PasswordField
          label={t.auth.reset.confirmPassword}
          name="confirm_password"
          autoComplete="new-password"
          required
          value={confirmation}
          onChange={(event) => setConfirmation(event.target.value)}
          error={localError.confirmation}
          showLabel={t.auth.login.showPassword}
          hideLabel={t.auth.login.hidePassword}
        />
        <Button type="submit" loading={submitting} loadingText={t.auth.reset.submitting}>
          {t.auth.reset.submit}
        </Button>
      </form>
    </div>
  );
}
