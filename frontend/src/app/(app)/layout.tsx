import type { ReactNode } from "react";

import { SessionGate } from "@/components/shell/SessionGate";
import { SessionProvider } from "@/lib/session/SessionProvider";

/**
 * Authenticated area. src/proxy.ts already sent visitors without a session cookie to the
 * login page; here the session itself is verified with the API before anything renders.
 */
export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <SessionProvider>
      <SessionGate>{children}</SessionGate>
    </SessionProvider>
  );
}
