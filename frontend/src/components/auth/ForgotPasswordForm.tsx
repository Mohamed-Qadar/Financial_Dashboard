"use client";

import Link from "next/link";
import { type FormEvent, useState } from "react";

import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { TextField } from "@/components/ui/Field";
import { auth } from "@/lib/api/endpoints";
import { ApiError } from "@/lib/api/errors";
import { useI18n } from "@/lib/i18n/LocaleProvider";

import { FormError } from "./FormError";

/**
 * Password reset request. The backend answers 202 whether or not the account exists, and
 * this page shows the same confirmation either way (no account enumeration).
 */
export function ForgotPasswordForm() {
  const { t } = useI18n();
  const [email, setEmail] = useState("");
  const [missing, setMissing] = useState(false);
  const [failure, setFailure] = useState<unknown>(null);
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (email.trim() === "") {
      setMissing(true);
      return;
    }
    setMissing(false);
    setSubmitting(true);
    setFailure(null);
    try {
      await auth.requestPasswordReset(email.trim());
      setSent(true);
    } catch (error) {
      setFailure(error);
    } finally {
      setSubmitting(false);
    }
  }

  if (sent) {
    return (
      <div className="auth-card">
        <h1>{t.auth.forgot.sentTitle}</h1>
        <Alert tone="success">{t.auth.forgot.sentBody}</Alert>
        <p className="auth-links">
          <Link href="/login">{t.auth.forgot.backToLogin}</Link>
        </p>
      </div>
    );
  }

  const fieldErrors = failure instanceof ApiError ? failure.fieldErrors() : {};
  return (
    <div className="auth-card">
      <div>
        <h1>{t.auth.forgot.title}</h1>
        <p className="auth-intro">{t.auth.forgot.intro}</p>
      </div>
      <FormError error={failure} />
      <form className="ui-form" noValidate onSubmit={onSubmit}>
        <TextField
          label={t.auth.login.email}
          name="email"
          type="email"
          autoComplete="email"
          inputMode="email"
          autoFocus
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          error={missing ? t.common.required : fieldErrors.email}
        />
        <Button type="submit" loading={submitting} loadingText={t.auth.forgot.submitting}>
          {t.auth.forgot.submit}
        </Button>
      </form>
      <p className="auth-links">
        <Link href="/login">{t.auth.forgot.backToLogin}</Link>
      </p>
    </div>
  );
}
