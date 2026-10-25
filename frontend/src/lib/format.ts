/**
 * Display formatting for values the API returns (codes, numbers).
 *
 * Somali does not come from Intl: Chrome ships without Somali locale data (measured:
 * `Intl.DateTimeFormat.supportedLocalesOf("so")` is empty, names fall back to English),
 * while Node has it, so server and browser would render different text (a hydration error)
 * and Somali screens would show English names. Somali names therefore come from the
 * tables below (CLDR 48 data, as printed by Node's ICU; review with the other Somali texts).
 * English uses Intl, which every runtime supports.
 *
 * Money (later modules): never rely on Intl's default fraction digits; ICU uses 0 for SOS,
 * while the currencies table says 2. Pass the currency's `minor_units` explicitly.
 */
import { intlLocale, type Locale } from "@/lib/i18n";

const SOMALI_MONTHS = [
  "Jannaayo",
  "Febraayo",
  "Maarso",
  "Abriil",
  "Maayo",
  "Juun",
  "Luulyo",
  "Ogosto",
  "Sebteembar",
  "Oktoobar",
  "Noofeembar",
  "Diseembar",
] as const;

const SOMALI_REGIONS: Record<string, string> = { SO: "Soomaaliya" };
const SOMALI_CURRENCIES: Record<string, string> = {
  USD: "Doolarka Mareeykanka",
  SOS: "Shilingka Soomaaliya",
};

function englishName(type: "region" | "currency", code: string): string {
  try {
    return new Intl.DisplayNames([intlLocale("en")], { type, fallback: "code" }).of(code) ?? code;
  } catch {
    return code;
  }
}

export function countryName(locale: Locale, code: string): string {
  return locale === "so" ? (SOMALI_REGIONS[code] ?? code) : englishName("region", code);
}

export function currencyName(locale: Locale, code: string): string {
  return locale === "so" ? (SOMALI_CURRENCIES[code] ?? code) : englishName("currency", code);
}

/** Month 1–12 as a name ("October" / "Oktoobar"). */
export function monthName(locale: Locale, month: number): string {
  if (!Number.isInteger(month) || month < 1 || month > 12) return String(month);
  if (locale === "so") return SOMALI_MONTHS[month - 1]!;
  return new Intl.DateTimeFormat(intlLocale("en"), { month: "long", timeZone: "UTC" }).format(
    new Date(Date.UTC(2024, month - 1, 1)),
  );
}

/** Initials for an avatar, from the full name or the e-mail address. */
export function initials(fullName: string, email: string): string {
  const source = fullName.trim() || email.split("@")[0] || "?";
  const parts = source.split(/[\s._-]+/).filter(Boolean);
  const letters = parts.length > 1 ? `${parts[0]![0]}${parts[1]![0]}` : source.slice(0, 2);
  return letters.toUpperCase();
}

export const MONOGRAM_TONES = ["blue", "indigo", "teal", "cyan", "violet", "slate"] as const;
export type MonogramTone = (typeof MONOGRAM_TONES)[number];

/** A stable colour for an id (same company, same colour everywhere). */
export function monogramTone(id: string): MonogramTone {
  let hash = 0;
  for (const char of id) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  return MONOGRAM_TONES[hash % MONOGRAM_TONES.length]!;
}

/** Up to two letters of a name, ignoring bracketed parts ("Hodan Foods (test)" → "HF"). */
export function monogramLetters(name: string): string {
  const words = name
    .replace(/\(.*?\)/g, " ")
    .split(/\s+/)
    .filter((word) => /\p{L}/u.test(word));
  const letters = words.length > 1 ? `${words[0]![0]}${words[1]![0]}` : (words[0] ?? "?").slice(0, 2);
  return letters.toUpperCase();
}

export function companyDisplayName(company: { trade_name: string; legal_name: string }): string {
  return company.trade_name.trim() || company.legal_name;
}
