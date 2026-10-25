import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { testCompany } from "@/test/fixtures";
import { renderWithI18n } from "@/test/i18n";

import { CompanyPicker } from "./CompanyPicker";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push }),
}));

vi.mock("@/lib/session/SessionProvider", () => ({
  useSession: () => ({ handleAuthError: () => false }),
}));

const list = vi.fn();
const select = vi.fn();
vi.mock("@/lib/api/endpoints", () => ({
  companies: { list: () => list(), select: (id: string) => select(id) },
}));

const ONE = testCompany();
const TWO = testCompany({
  id: "55555555-5555-4555-8555-555555555555",
  code: "T9",
  legal_name: "Other Test Ltd",
  tenant: { id: "66666666-6666-4666-8666-666666666666", name: "Second Test Business" },
});

beforeEach(() => vi.clearAllMocks());

describe("CompanyPicker", () => {
  it("groups companies by business and opens the chosen one", async () => {
    list.mockResolvedValue([ONE, TWO]);
    select.mockResolvedValue(TWO);
    renderWithI18n(<CompanyPicker auto={false} />);

    expect(await screen.findByRole("heading", { name: "Second Test Business" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Open company: Other Test Ltd" }));

    await waitFor(() => expect(push).toHaveBeenCalledWith(`/c/${TWO.id}`));
    expect(select).toHaveBeenCalledWith(TWO.id);
  });

  it("opens the only company directly after login", async () => {
    list.mockResolvedValue([ONE]);
    select.mockResolvedValue(ONE);
    renderWithI18n(<CompanyPicker auto />);

    await waitFor(() => expect(push).toHaveBeenCalledWith(`/c/${ONE.id}`));
    expect(select).toHaveBeenCalledTimes(1);
  });

  it("does not auto-open when the user came back on purpose", async () => {
    list.mockResolvedValue([ONE]);
    renderWithI18n(<CompanyPicker auto={false} />);

    await screen.findByRole("button", { name: `Open company: ${ONE.legal_name}` });
    expect(select).not.toHaveBeenCalled();
  });

  it("explains when there is no company", async () => {
    list.mockResolvedValue([]);
    renderWithI18n(<CompanyPicker auto />);

    expect(await screen.findByText("No companies available")).toBeTruthy();
  });

  it("says why the user was sent here", async () => {
    list.mockResolvedValue([ONE]);
    renderWithI18n(<CompanyPicker auto notice="unavailable" />);

    expect(screen.getByRole("status").textContent).toContain("That company is not available");
    await screen.findByRole("button", { name: `Open company: ${ONE.legal_name}` });
    expect(select).not.toHaveBeenCalled(); // no auto-open after an unavailable company
  });
});
