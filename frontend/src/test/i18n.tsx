import { render } from "@testing-library/react";
import type { ReactElement } from "react";

import type { Locale } from "@/lib/i18n";
import { LocaleProvider } from "@/lib/i18n/LocaleProvider";

/** Render inside the locale provider. Test files must mock `next/navigation`. */
export function renderWithI18n(ui: ReactElement, locale: Locale = "en") {
  return render(<LocaleProvider locale={locale}>{ui}</LocaleProvider>);
}
