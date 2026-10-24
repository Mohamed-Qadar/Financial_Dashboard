"use client";

import { type FormEvent, useState, useSyncExternalStore } from "react";

import { FormError } from "@/components/auth/FormError";
import { Alert } from "@/components/ui/Alert";
import { Button, ButtonLink } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { PasswordField } from "@/components/ui/Field";
import { PageHeader } from "@/components/ui/States";
import { auth } from "@/lib/api/endpoints";
import { ApiError, isApiError } from "@/lib/api/errors";
import { useI18n } from "@/lib/i18n/LocaleProvider";
import { rememberedCompany } from "@/lib/session/companyMemory";
import { useSession, useUser } from "@/lib/session/SessionProvider";

const noSubscription = () => () => undefined;

/**
 * Profile (read-only until milestone 2.7 adds profile updates) and password change. The
 * backend keeps this session under a new key and ends every other session of the user.
 */
export function AccountView() {
  const { t } = useI18n();
  const user = useUser();
  const { handleAuthError } = useSession();
  // This tab's last company, only for the "back" link (see companyMemory).
  const backCompany = useSyncExternalStore(noSubscription, rememberedCompany, () => null);

  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [localError, setLocalError] = useState<Record<string, string | undefined>>({});
  const [failure, setFailure] = useState<unknown>(null);
  const [submitting, setSubmitting] = useState(false);
  const [changed, setChanged] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const errors = {
      current: current === "" ? t.common.required : undefined,
      next: next === "" ? t.common.required : undefined,
      confirmation:
        confirmation === "" ? t.common.required : confirmation !== next ? t.auth.reset.mismatch : undefined,
    };
    setLocalError(errors);
    setChanged(false);
    if (errors.current || errors.next || errors.confirmation) return;

    setSubmitting(true);
    setFailure(null);
    try {
      await auth.changePassword(current, next);
      setCurrent("");
      setNext("");
      setConfirmation("");
      setChanged(true);
    } catch (error) {
      if (handleAuthError(error)) return;
      if (isApiError(error, "invalid_current_password")) {
        setLocalError({ current: t.errors.invalid_current_password });
        setCurrent("");
      } else {
        setFailure(error);
      }
    } finally {
      setSubmitting(false);
    }
  }

  const fieldErrors = failure instanceof ApiError ? failure.fieldErrors() : {};

  return (
    <>
      <PageHeader
        title={t.account.title}
        actions={
          backCompany ? (
            <ButtonLink href={`/c/${backCompany}`} icon="chevronLeft">
              {t.account.backToCompany}
            </ButtonLink>
          ) : null
        }
      />
      <div className="narrow-page">
        <Card title={t.account.profile}>
          <dl className="ui-details">
            <dt>{t.account.email}</dt>
            <dd>{user.email}</dd>
            <dt>{t.account.fullName}</dt>
            <dd>{user.full_name.trim() || t.account.notSet}</dd>
          </dl>
        </Card>
        <Card title={t.account.changePassword}>
          {changed ? <Alert tone="success">{t.account.success}</Alert> : null}
          <FormError error={failure} />
          <form className="ui-form account-form" noValidate onSubmit={onSubmit}>
            <PasswordField
              label={t.account.currentPassword}
              name="current_password"
              autoComplete="current-password"
              required
              value={current}
              onChange={(event) => setCurrent(event.target.value)}
              error={localError.current ?? fieldErrors.current_password}
              showLabel={t.auth.login.showPassword}
              hideLabel={t.auth.login.hidePassword}
            />
            <PasswordField
              label={t.auth.reset.newPassword}
              name="new_password"
              autoComplete="new-password"
              required
              hint={t.auth.reset.hint}
              value={next}
              onChange={(event) => setNext(event.target.value)}
              error={localError.next ?? fieldErrors.new_password}
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
              {t.account.changePassword}
            </Button>
          </form>
        </Card>
      </div>
    </>
  );
}
