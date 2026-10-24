"use client";

import { LOCALES } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/LocaleProvider";

/** Somali / English toggle. The choice is a cookie preference; no data is sent anywhere. */
export function LanguageSwitcher() {
  const { locale, t, setLocale } = useI18n();
  return (
    <div className="ui-segmented" role="group" aria-label={t.common.language}>
      {LOCALES.map((option) => (
        <button
          key={option}
          type="button"
          lang={option}
          aria-pressed={option === locale}
          onClick={() => option !== locale && setLocale(option)}
        >
          <span aria-hidden="true">{option.toUpperCase()}</span>
          <span className="visually-hidden">{t.common.languages[option]}</span>
        </button>
      ))}
    </div>
  );
}
