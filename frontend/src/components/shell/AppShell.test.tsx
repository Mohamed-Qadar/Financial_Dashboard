import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithI18n } from "@/test/i18n";
import { testCompany, TEST_USER } from "@/test/fixtures";
import { setViewport } from "@/test/setup";

import { AppShell } from "./AppShell";

const push = vi.fn();
let pathname = "/c/22222222-2222-4222-8222-222222222222";
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push }),
  usePathname: () => pathname,
}));

const list = vi.fn();
const select = vi.fn();
vi.mock("@/lib/api/endpoints", () => ({
  companies: { list: () => list(), select: (id: string) => select(id) },
  auth: { logout: vi.fn() },
}));

const signOut = vi.fn();
vi.mock("@/lib/session/SessionProvider", () => ({
  useSession: () => ({ signOut, handleAuthError: () => false }),
  useUser: () => TEST_USER,
}));

const COMPANY = testCompany();
const OTHER = testCompany({
  id: "44444444-4444-4444-8444-444444444444",
  code: "T2",
  legal_name: "Test Company Two Ltd",
});

beforeEach(() => {
  vi.clearAllMocks();
  pathname = `/c/${COMPANY.id}`;
});

describe("AppShell", () => {
  it("shows only navigation that exists and marks the current page", () => {
    renderWithI18n(<AppShell company={COMPANY}>content</AppShell>);

    const nav = screen.getByRole("navigation", { name: "Main navigation" });
    const links = Array.from(nav.querySelectorAll("a")).map((a) => a.textContent);
    expect(links).toEqual(["Overview", "Companies", "Account"]);
    expect(screen.getByRole("link", { name: "Overview" }).getAttribute("aria-current")).toBe("page");
    expect(screen.getByRole("main").textContent).toBe("content");
  });

  it("collapses the sidebar on desktop and remembers it", () => {
    renderWithI18n(<AppShell company={COMPANY}>x</AppShell>);
    const toggle = screen.getByRole("button", { name: "Collapse sidebar" });
    expect(toggle.getAttribute("aria-expanded")).toBe("true");

    fireEvent.click(toggle);

    expect(screen.getByRole("button", { name: "Expand sidebar" }).getAttribute("aria-expanded")).toBe("false");
    expect(localStorage.getItem("erp.sidebarCollapsed")).toBe("1");
    // Labels stay available to screen readers when only icons are visible.
    expect(screen.getByRole("link", { name: "Account" })).toBeTruthy();
  });

  it("opens a drawer on small screens that Escape closes, returning focus", async () => {
    setViewport("mobile");
    renderWithI18n(<AppShell company={COMPANY}>x</AppShell>);
    const toggle = screen.getByRole("button", { name: "Open menu" });

    fireEvent.click(toggle);

    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(document.querySelector(".shell-main")?.hasAttribute("inert")).toBe(true);
    await waitFor(() => expect(document.activeElement?.closest("#app-sidebar")).not.toBeNull());

    act(() => {
      fireEvent.keyDown(document, { key: "Escape" });
    });

    expect(screen.getByRole("button", { name: "Open menu" }).getAttribute("aria-expanded")).toBe("false");
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Open menu" }));
    expect(document.querySelector("#app-sidebar")?.hasAttribute("inert")).toBe(true);
  });

  it("switches company: records the switch, then opens the company's URL", async () => {
    list.mockResolvedValue([COMPANY, OTHER]);
    select.mockResolvedValue(OTHER);
    renderWithI18n(<AppShell company={COMPANY}>x</AppShell>);

    fireEvent.click(screen.getByRole("button", { name: /Active company/ }));
    const other = await screen.findByRole("menuitemradio", { name: /Test Company Two Ltd/ });
    expect(screen.getByRole("menuitemradio", { name: /Test Company One Ltd/ }).getAttribute("aria-checked")).toBe("true");
    expect(screen.getByRole("group", { name: "Test Business" })).toBeTruthy();

    fireEvent.click(other);

    await waitFor(() => expect(push).toHaveBeenCalledWith(`/c/${OTHER.id}`));
    expect(select).toHaveBeenCalledWith(OTHER.id);
  });

  it("does not navigate when recording the switch fails", async () => {
    const { ApiError } = await import("@/lib/api/errors");
    list.mockResolvedValue([COMPANY, OTHER]);
    select.mockRejectedValue(new ApiError(503, "service_unavailable", "x", "req-7"));
    renderWithI18n(<AppShell company={COMPANY}>x</AppShell>);

    fireEvent.click(screen.getByRole("button", { name: /Active company/ }));
    fireEvent.click(await screen.findByRole("menuitemradio", { name: /Test Company Two Ltd/ }));

    expect((await screen.findByRole("alert")).textContent).toContain("temporarily unavailable");
    expect(screen.getByRole("alert").textContent).toContain("req-7");
    expect(push).not.toHaveBeenCalled();
  });

  it("offers account settings and sign-out in the user menu", () => {
    signOut.mockResolvedValue(undefined);
    renderWithI18n(<AppShell company={null}>x</AppShell>);

    fireEvent.click(screen.getByRole("button", { name: /User menu/ }));
    expect(screen.getByText(TEST_USER.email)).toBeTruthy();
    expect(screen.getByRole("menuitem", { name: "Account settings" }).getAttribute("href")).toBe("/account");

    fireEvent.click(screen.getByRole("menuitem", { name: "Sign out" }));

    expect(signOut).toHaveBeenCalledTimes(1);
  });

  it("without an active company, links to the company picker", () => {
    pathname = "/account";
    renderWithI18n(<AppShell company={null}>x</AppShell>);

    expect(screen.getByRole("link", { name: "Select company" }).getAttribute("href")).toBe("/select-company");
    expect(screen.queryByRole("link", { name: "Overview" })).toBeNull();
  });
});
