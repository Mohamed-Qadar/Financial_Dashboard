"use client";

import { CompanyHome } from "@/components/company/CompanyHome";
import { AppShell } from "@/components/shell/AppShell";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { PasswordField, TextField } from "@/components/ui/Field";
import { Menu, MenuItem } from "@/components/ui/Menu";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState, ErrorState, PageHeader, Skeleton } from "@/components/ui/States";
import { ApiError } from "@/lib/api/errors";
import { StaticCompanyProvider } from "@/lib/company/CompanyProvider";
import { useI18n } from "@/lib/i18n/LocaleProvider";
import { StaticSessionProvider } from "@/lib/session/SessionProvider";

import { PREVIEW_COMPANY, PREVIEW_USER } from "./previewData";

/** Every reusable component in its states, inside the real shell, with preview data only. */
export function UiPreview() {
  const { t } = useI18n();
  return (
    <StaticSessionProvider user={PREVIEW_USER}>
      <StaticCompanyProvider company={PREVIEW_COMPANY}>
        <div className="preview-banner" role="note">
          {t.common.previewBanner}
        </div>
        <AppShell company={PREVIEW_COMPANY}>
          <CompanyHome />
          <PageHeader title="UI kit" description="Development only. Not available in production builds." />
          <div className="home-grid">
            <Card title="Buttons">
              <div className="ui-button-row">
                <Button>Primary</Button>
                <Button variant="secondary">Secondary</Button>
                <Button variant="ghost">Ghost</Button>
                <Button variant="danger">Danger</Button>
                <Button loading loadingText="Saving…">
                  Save
                </Button>
                <Button size="sm" icon="check">
                  Small
                </Button>
                <Button disabled>Disabled</Button>
              </div>
            </Card>
            <Card title="Feedback">
              <Alert tone="info">Information message.</Alert>
              <Alert tone="success">Saved successfully.</Alert>
              <Alert tone="warning">Please check this.</Alert>
              <Alert tone="danger" reference="00000000-0000-4000-8000-0000000000ff" referenceLabel={t.common.reference}>
                Something failed.
              </Alert>
              <div className="ui-button-row">
                <span className="ui-badge" data-tone="success">Active</span>
                <span className="ui-badge" data-tone="warning">Pending</span>
                <span className="ui-badge" data-tone="danger">Disabled</span>
                <span className="ui-badge" data-tone="info">Info</span>
                <span className="ui-badge">Neutral</span>
              </div>
              <Spinner label={t.common.loading} />
            </Card>
            <Card title="Form fields">
              <form className="ui-form" noValidate onSubmit={(event) => event.preventDefault()}>
                <TextField label="Text field" name="preview_text" hint="Helpful hint text." />
                <TextField label="Invalid field" name="preview_invalid" defaultValue="wrong" error="This value is not valid." required />
                <PasswordField label="Password" name="preview_password" autoComplete="off" showLabel="Show" hideLabel="Hide" />
              </form>
            </Card>
            <Card title="Menu">
              <Menu label="Example menu" align="start" trigger="Open example menu">
                <MenuItem onSelect={() => undefined}>First action</MenuItem>
                <MenuItem onSelect={() => undefined} checked>
                  Selected option
                </MenuItem>
                <MenuItem onSelect={() => undefined} disabled>
                  Disabled action
                </MenuItem>
              </Menu>
            </Card>
            <Card title="Loading">
              <Skeleton />
              <Skeleton width="medium" />
              <Skeleton width="short" />
            </Card>
            <Card title="Empty and error states">
              <EmptyState icon="building" title="Nothing here yet">
                Explains what will appear and why it is empty.
              </EmptyState>
              <ErrorState error={new ApiError(503, "service_unavailable", "x", "00000000-0000-4000-8000-0000000000ee")} onRetry={() => undefined} />
            </Card>
          </div>
        </AppShell>
      </StaticCompanyProvider>
    </StaticSessionProvider>
  );
}
