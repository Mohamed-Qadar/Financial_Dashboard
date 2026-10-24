"use client";

import { usePathname, useRouter } from "next/navigation";
import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import { auth } from "@/lib/api/endpoints";
import { ApiError, isApiError } from "@/lib/api/errors";
import type { User } from "@/lib/api/types";
import { loginPath } from "@/lib/redirects";

import { clearRememberedCompany } from "./companyMemory";

type SessionState =
  | { status: "loading" }
  | { status: "authenticated"; user: User }
  | { status: "error"; error: unknown };

interface SessionContextValue {
  state: SessionState;
  reload: () => void;
  /** Ends the session on the server, forgets the tab's company and goes to the login page. */
  signOut: () => Promise<void>;
  /** For any API error: sends the user to the login page if the session has ended. */
  handleAuthError: (error: unknown) => boolean;
}

const SessionContext = createContext<SessionContextValue | null>(null);

/**
 * Loads the signed-in user (`GET /api/v1/auth/me/`) for the authenticated area. The server is
 * the authority: a 403 `not_authenticated` from any call leads to the login page.
 */
export function SessionProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [state, setState] = useState<SessionState>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  const handleAuthError = useCallback(
    (error: unknown) => {
      if (isApiError(error, "not_authenticated")) {
        clearRememberedCompany();
        router.replace(loginPath(pathname, "expired"));
        return true;
      }
      return false;
    },
    [pathname, router],
  );

  useEffect(() => {
    const controller = new AbortController();
    auth
      .me(controller.signal)
      .then((user) => setState({ status: "authenticated", user }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        if (!handleAuthError(error)) setState({ status: "error", error });
      });
    return () => controller.abort();
    // Load once per mount (and on explicit reload); route changes reuse the session.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [attempt]);

  const reload = useCallback(() => {
    setState({ status: "loading" });
    setAttempt((value) => value + 1);
  }, []);

  const signOut = useCallback(async () => {
    try {
      await auth.logout();
    } catch (error) {
      // The session may already be gone; anything else is reported to the caller.
      if (!(error instanceof ApiError && error.code === "not_authenticated")) throw error;
    }
    clearRememberedCompany();
    router.replace("/login");
    router.refresh();
  }, [router]);

  const value = useMemo(
    () => ({ state, reload, signOut, handleAuthError }),
    [state, reload, signOut, handleAuthError],
  );
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

/**
 * A fixed signed-in state without any API call, for the development UI preview only
 * (src/app/ui-preview). It grants nothing: every API call still needs a real session.
 */
export function StaticSessionProvider({ user, children }: { user: User; children: ReactNode }) {
  const value = useMemo<SessionContextValue>(
    () => ({
      state: { status: "authenticated", user },
      reload: () => undefined,
      signOut: async () => undefined,
      handleAuthError: () => false,
    }),
    [user],
  );
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const value = useContext(SessionContext);
  if (value === null) throw new Error("useSession() must be used inside <SessionProvider>.");
  return value;
}

/** The signed-in user; only for components rendered after the session has loaded. */
export function useUser(): User {
  const { state } = useSession();
  if (state.status !== "authenticated") throw new Error("No authenticated user yet.");
  return state.user;
}
