"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";

import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { PasswordField, TextField } from "@/components/ui/Field";
import { auth } from "@/lib/api/endpoints";
import { ApiError, isApiError } from "@/lib/api/errors";
import { useI18n } from "@/lib/i18n/LocaleProvider";

import { FormError } from "./FormError";

/** Email + password sign-in (POST /api/v1/auth/login/; CSRF handled by the API client). */
export function LoginForm({ next, expired }: { next: string; expired: boolean }) {
  const { t } = useI18n();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [missing, setMissing] = useState<{ email?: boolean; password?: boolean }>({});
  const [failure, setFailure] = useState<unknown>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const empty = { email: email.trim() === "", password: password === "" };
    setMissing(empty);
    if (empty.email || empty.password) return;

    setSubmitting(true);
    setFailure(null);
    try {
      await auth.login(email.trim(), password);
      router.replace(next);
      router.refresh();
    } catch (error) {
      setFailure(error);
      if (isApiError(error, "invalid_credentials")) setPassword("");
      setSubmitting(false);
    }
  }

  const fieldErrors = failure instanceof ApiError ? failure.fieldErrors() : {};

  return (
    <div className="auth-card">
      <div>
        <h1>{t.auth.login.title}</h1>
        <p className="auth-intro">{t.auth.login.subtitle}</p>
      </div>
      {expired && failure === null ? <Alert tone="info">{t.auth.login.sessionExpired}</Alert> : null}
      <FormError error={failure} />
      <form className="ui-form" noValidate onSubmit={onSubmit}>
        <TextField
          label={t.auth.login.email}
          name="email"
          type="email"
          autoComplete="username"
          inputMode="email"
          autoFocus
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          error={missing.email ? t.common.required : fieldErrors.email}
        />
        <PasswordField
          label={t.auth.login.password}
          name="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          error={missing.password ? t.common.required : fieldErrors.password}
          showLabel={t.auth.login.showPassword}
          hideLabel={t.auth.login.hidePassword}
        />
        <Button type="submit" loading={submitting} loadingText={t.auth.login.submitting}>
          {t.auth.login.submit}
        </Button>
      </form>
      <p className="auth-links">
        <Link href="/forgot-password">{t.auth.login.forgot}</Link>
      </p>
    </div>
  );
}
