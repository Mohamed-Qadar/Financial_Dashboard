/**
 * Somali / English localization (decision D8): typed dictionaries, no locale in the URL,
 * Somali by default. The visitor's choice is kept in the `erp_lang` cookie (a preference, not
 * a credential). The account's `preferred_language` is not used yet: it cannot be changed
 * through the API before milestone 2.7.
 */
import { en, type Messages } from "./messages/en";
import { so } from "./messages/so";

export type { Messages };

export const LOCALES = ["so", "en"] as const;
export type Locale = (typeof LOCALES)[number];

export const DEFAULT_LOCALE: Locale = "so";
export const LOCALE_COOKIE = "erp_lang";
const ONE_YEAR_SECONDS = 365 * 24 * 60 * 60;

const DICTIONARIES: Record<Locale, Messages> = { so, en };

export function isLocale(value: unknown): value is Locale {
  return typeof value === "string" && (LOCALES as readonly string[]).includes(value);
}

/** Any unknown or missing value falls back to Somali. */
export function resolveLocale(value: unknown): Locale {
  return isLocale(value) ? value : DEFAULT_LOCALE;
}

export function getMessages(locale: Locale): Messages {
  return DICTIONARIES[locale];
}

/** The `Set-Cookie`-style string for `document.cookie`. */
export function localeCookie(locale: Locale): string {
  return `${LOCALE_COOKIE}=${locale}; Path=/; Max-Age=${ONE_YEAR_SECONDS}; SameSite=Lax`;
}

/** BCP 47 tag for `Intl` formatting (ICU supports both, e.g. "Oktoobar" in Somali). */
export function intlLocale(locale: Locale): string {
  return locale === "so" ? "so-SO" : "en-GB";
}
