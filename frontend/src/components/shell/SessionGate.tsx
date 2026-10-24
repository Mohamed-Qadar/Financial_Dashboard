"use client";

import type { ReactNode } from "react";

import { ErrorState, PageLoading } from "@/components/ui/States";
import { useSession } from "@/lib/session/SessionProvider";

/** Renders the authenticated area only after `GET me/` succeeded. */
export function SessionGate({ children }: { children: ReactNode }) {
  const { state, reload } = useSession();
  if (state.status === "loading") {
    return (
      <main id="main-content">
        <PageLoading />
      </main>
    );
  }
  if (state.status === "error") {
    return (
      <main id="main-content">
        <ErrorState error={state.error} onRetry={reload} />
      </main>
    );
  }
  return <>{children}</>;
}
