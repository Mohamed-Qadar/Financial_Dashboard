"use client";

import { createContext, type ReactNode, useCallback, useContext, useMemo, useState } from "react";

import { FormError } from "@/components/auth/FormError";
import { Button } from "@/components/ui/Button";
import { useI18n } from "@/lib/i18n/LocaleProvider";

const NoticeContext = createContext<((error: unknown) => void) | null>(null);

/** Shows the error of a shell action (switching company, signing out) above the page. */
export function ShellNoticeProvider({ children }: { children: ReactNode }) {
  const { t } = useI18n();
  const [error, setError] = useState<unknown>(null);
  const show = useCallback((value: unknown) => setError(value), []);
  const value = useMemo(() => show, [show]);
  return (
    <NoticeContext.Provider value={value}>
      {error !== null ? (
        <div className="shell-notice">
          <FormError error={error} />
          <Button variant="ghost" size="sm" icon="close" onClick={() => setError(null)}>
            {t.common.close}
          </Button>
        </div>
      ) : null}
      {children}
    </NoticeContext.Provider>
  );
}

export function useShellNotice(): (error: unknown) => void {
  const value = useContext(NoticeContext);
  if (value === null) throw new Error("useShellNotice() must be used inside <ShellNoticeProvider>.");
  return value;
}
