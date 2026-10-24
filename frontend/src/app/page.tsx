import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { DEFAULT_AFTER_LOGIN } from "@/lib/redirects";
import { SESSION_COOKIE } from "@/lib/security";

/**
 * Start page: straight to the company picker when a session cookie exists, otherwise to the
 * login page. The cookie is only a hint; the API decides whether the session is valid.
 */
export default async function StartPage() {
  const store = await cookies();
  redirect(store.has(SESSION_COOKIE) ? DEFAULT_AFTER_LOGIN : "/login");
}
