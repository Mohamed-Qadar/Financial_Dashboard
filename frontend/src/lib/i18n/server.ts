// Server components only (next/headers is not available in the browser).
import { cookies } from "next/headers";

import { LOCALE_COOKIE, type Locale, resolveLocale } from "./index";

/** The visitor's language for server rendering (cookie, else Somali). */
export async function getRequestLocale(): Promise<Locale> {
  const store = await cookies();
  return resolveLocale(store.get(LOCALE_COOKIE)?.value);
}
