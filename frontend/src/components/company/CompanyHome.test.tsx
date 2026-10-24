import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { testCompany, TEST_USER } from "@/test/fixtures";
import { renderWithI18n } from "@/test/i18n";

import { CompanyHome } from "./CompanyHome";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }),
}));
const COMPANY = testCompany();
vi.mock("@/lib/company/CompanyProvider", () => ({ useCompany: () => COMPANY }));
vi.mock("@/lib/session/SessionProvider", () => ({ useUser: () => TEST_USER }));
vi.mock("@/lib/health", () => ({
  getSystemStatus: () => Promise.resolve({ api: "ok", database: "ok" }),
}));

beforeEach(() => vi.clearAllMocks());

describe("CompanyHome", () => {
  it("shows the company record from the API, localized", async () => {
    renderWithI18n(<CompanyHome />);

    expect(screen.getByRole("heading", { name: "Overview" })).toBeTruthy();
    expect(screen.getByText("Welcome, Test User")).toBeTruthy();
    expect(screen.getByText(COMPANY.legal_name)).toBeTruthy();
    expect(screen.getByText("Somalia")).toBeTruthy();
    expect(screen.getByText("July")).toBeTruthy();
    expect(await screen.findAllByText("Operational")).toHaveLength(2);
  });

  it("uses Somali names for country and month", () => {
    renderWithI18n(<CompanyHome />, "so");

    expect(screen.getByRole("heading", { name: "Guudmar" })).toBeTruthy();
    expect(screen.getByText("Luulyo")).toBeTruthy();
  });

  it("contains no business figures: every number on the page comes from the API record", () => {
    renderWithI18n(<CompanyHome />);

    // Strip the values the API returned; nothing numeric (amounts, counts, KPIs) may remain.
    let text = document.body.textContent ?? "";
    for (const value of [COMPANY.code, COMPANY.timezone, TEST_USER.email]) {
      text = text.replaceAll(value, "");
    }
    expect(text).not.toMatch(/\d/);
    expect(screen.getByText(/will appear here when those modules are released/)).toBeTruthy();
  });
});
