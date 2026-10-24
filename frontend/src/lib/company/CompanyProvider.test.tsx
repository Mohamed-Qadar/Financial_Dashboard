import { screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api/errors";
import { rememberedCompany } from "@/lib/session/companyMemory";
import { testCompany } from "@/test/fixtures";
import { renderWithI18n } from "@/test/i18n";

import { CompanyProvider, useCompany } from "./CompanyProvider";

const replace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, refresh: vi.fn(), push: vi.fn() }),
}));

const handleAuthError = vi.fn(() => false);
vi.mock("@/lib/session/SessionProvider", () => ({
  useSession: () => ({ handleAuthError }),
}));

const active = vi.fn();
vi.mock("@/lib/api/endpoints", () => ({
  companies: { active: (...args: unknown[]) => active(...args) },
}));

const COMPANY = testCompany();

function Probe() {
  return <p>{useCompany().legal_name}</p>;
}

beforeEach(() => vi.clearAllMocks());

describe("CompanyProvider", () => {
  it("shows the company only after the server verified the URL's company", async () => {
    let resolve: (value: unknown) => void = () => undefined;
    active.mockReturnValue(new Promise((r) => (resolve = r)));
    renderWithI18n(
      <CompanyProvider companyId={COMPANY.id}>
        <Probe />
      </CompanyProvider>,
    );

    expect(screen.getByRole("status").textContent).toContain("Loading");
    expect(active.mock.calls[0]![0]).toBe(COMPANY.id);

    resolve(COMPANY);

    expect(await screen.findByText(COMPANY.legal_name)).toBeTruthy();
    expect(rememberedCompany()).toBe(COMPANY.id);
  });

  it.each([
    new ApiError(404, "not_found", "Not found."),
    new ApiError(400, "company_required", "x"),
  ])("sends an inaccessible company (%s) back to the picker", async (error) => {
    active.mockRejectedValue(error);
    renderWithI18n(
      <CompanyProvider companyId={COMPANY.id}>
        <Probe />
      </CompanyProvider>,
    );

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/select-company?notice=unavailable"));
    expect(screen.queryByText(COMPANY.legal_name)).toBeNull();
  });

  it("never calls the API with a malformed id from the URL", async () => {
    renderWithI18n(
      <CompanyProvider companyId="../../admin">
        <Probe />
      </CompanyProvider>,
    );

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/select-company?notice=unavailable"));
    expect(active).not.toHaveBeenCalled();
  });

  it("offers a retry for other failures", async () => {
    active.mockRejectedValueOnce(new ApiError(0, "network_error", "offline")).mockResolvedValue(COMPANY);
    renderWithI18n(
      <CompanyProvider companyId={COMPANY.id}>
        <Probe />
      </CompanyProvider>,
    );

    (await screen.findByRole("button", { name: "Try again" })).click();

    expect(await screen.findByText(COMPANY.legal_name)).toBeTruthy();
  });
});
