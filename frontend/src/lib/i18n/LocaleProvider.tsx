"use client";

import { useRouter } from "next/navigation";
import { createContext, type ReactNode, useCallback, useContext, useMemo } from "react";

import { getMessages, type Locale, localeCookie, type Messages } from "./index";

interface LocaleContextValue {
  locale: Locale;
  t: Messages;
  setLocale: (locale: Locale) => void;
}

const LocaleContext = createContext<LocaleContextValue | null>(null);

/**
 * Provides the messages of the language chosen on the server (root layout). Changing the
 * language stores the cookie and re-renders the server components, so `<html lang>` and all
 * server-rendered text follow.
 */
export function LocaleProvider({ locale, children }: { locale: Locale; children: ReactNode }) {
  const router = useRouter();
  const setLocale = useCallback(
    (next: Locale) => {
      document.cookie = localeCookie(next);
      router.refresh();
    },
    [router],
  );
  const value = useMemo(
    () => ({ locale, t: getMessages(locale), setLocale }),
    [locale, setLocale],
  );
  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

export function useI18n(): LocaleContextValue {
  const value = useContext(LocaleContext);
  if (value === null) {
    throw new Error("useI18n() must be used inside <LocaleProvider>.");
  }
  return value;
}
