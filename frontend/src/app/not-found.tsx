import { Brand } from "@/components/Brand";
import { ButtonLink } from "@/components/ui/Button";
import { getMessages } from "@/lib/i18n";
import { getRequestLocale } from "@/lib/i18n/server";

/** Unknown pages. The same text is used for pages the user may not see (nothing is revealed). */
export default async function NotFound() {
  const t = getMessages(await getRequestLocale());
  return (
    <main id="main-content" className="standalone-page">
      <div className="ui-card">
        <Brand name={t.common.appName} />
        <h1>{t.pages.notFoundTitle}</h1>
        <p>{t.pages.notFoundBody}</p>
        <div>
          <ButtonLink href="/" variant="primary">
            {t.pages.goHome}
          </ButtonLink>
        </div>
      </div>
    </main>
  );
}
