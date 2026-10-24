import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api/errors";

import { rememberCompany, rememberedCompany } from "./companyMemory";
import { SessionProvider, useSession } from "./SessionProvider";

const replace = vi.fn();
const refresh = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, refresh, push: vi.fn() }),
  usePathname: () => "/c/6d6fc62d-05a1-41cf-b6e9-de1990e18288",
}));

const me = vi.fn();
const logout = vi.fn();
vi.mock("@/lib/api/endpoints", () => ({
  auth: { me: (...args: unknown[]) => me(...args), logout: () => logout() },
}));

function Probe() {
  const { state, signOut } = useSession();
  return (
    <div>
      <span>{state.status === "authenticated" ? state.user.email : state.status}</span>
      <button onClick={() => void signOut()}>out</button>
    </div>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
});

describe("SessionProvider", () => {
  it("loads the signed-in user", async () => {
    me.mockResolvedValue({ id: "u", email: "hodan@example.com", full_name: "", preferred_language: "so" });

    render(<SessionProvider><Probe /></SessionProvider>);

    expect(await screen.findByText("hodan@example.com")).toBeTruthy();
    expect(replace).not.toHaveBeenCalled();
  });

  it("sends an ended session to the login page and back afterwards", async () => {
    me.mockRejectedValue(new ApiError(403, "not_authenticated", "No session."));
    rememberCompany("6d6fc62d-05a1-41cf-b6e9-de1990e18288");

    render(<SessionProvider><Probe /></SessionProvider>);

    await waitFor(() =>
      expect(replace).toHaveBeenCalledWith(
        "/login?next=%2Fc%2F6d6fc62d-05a1-41cf-b6e9-de1990e18288&reason=expired",
      ),
    );
    expect(rememberedCompany()).toBeNull();
  });

  it("shows other failures instead of redirecting", async () => {
    me.mockRejectedValue(new ApiError(0, "network_error", "offline"));

    render(<SessionProvider><Probe /></SessionProvider>);

    expect(await screen.findByText("error")).toBeTruthy();
    expect(replace).not.toHaveBeenCalled();
  });

  it("signs out on the server, forgets the tab's company and goes to login", async () => {
    me.mockResolvedValue({ id: "u", email: "hodan@example.com", full_name: "", preferred_language: "so" });
    logout.mockResolvedValue(undefined);
    rememberCompany("6d6fc62d-05a1-41cf-b6e9-de1990e18288");
    render(<SessionProvider><Probe /></SessionProvider>);
    await screen.findByText("hodan@example.com");

    screen.getByText("out").click();

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
    expect(logout).toHaveBeenCalledTimes(1);
    expect(rememberedCompany()).toBeNull();
  });
});
