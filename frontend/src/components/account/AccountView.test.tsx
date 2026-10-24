import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api/errors";
import { rememberCompany } from "@/lib/session/companyMemory";
import { TEST_USER } from "@/test/fixtures";
import { renderWithI18n } from "@/test/i18n";

import { AccountView } from "./AccountView";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }),
}));
const handleAuthError = vi.fn(() => false);
vi.mock("@/lib/session/SessionProvider", () => ({
  useUser: () => TEST_USER,
  useSession: () => ({ handleAuthError }),
}));
const changePassword = vi.fn();
vi.mock("@/lib/api/endpoints", () => ({
  auth: { changePassword: (...args: unknown[]) => changePassword(...args) },
}));

function fill(current: string, next: string, confirmation = next) {
  fireEvent.change(screen.getByLabelText(/^Current password/), { target: { value: current } });
  fireEvent.change(screen.getByLabelText(/^New password/), { target: { value: next } });
  fireEvent.change(screen.getByLabelText(/^Confirm new password/), { target: { value: confirmation } });
  fireEvent.click(screen.getByRole("button", { name: "Change password" }));
}

beforeEach(() => vi.clearAllMocks());

describe("AccountView", () => {
  it("shows the profile read-only", () => {
    renderWithI18n(<AccountView />);

    expect(screen.getByText(TEST_USER.email)).toBeTruthy();
    expect(screen.getByText(TEST_USER.full_name)).toBeTruthy();
    expect(screen.queryByRole("textbox")).toBeNull();
  });

  it("changes the password and clears the form", async () => {
    changePassword.mockResolvedValue(undefined);
    renderWithI18n(<AccountView />);

    fill("Old-phrase-123", "A-new-long-phrase-9");

    expect((await screen.findByRole("status")).textContent).toContain("Your password has been changed");
    expect(changePassword).toHaveBeenCalledWith("Old-phrase-123", "A-new-long-phrase-9");
    expect((screen.getByLabelText(/^New password/) as HTMLInputElement).value).toBe("");
  });

  it("marks a wrong current password on its field", async () => {
    changePassword.mockRejectedValue(new ApiError(400, "invalid_current_password", "x"));
    renderWithI18n(<AccountView />);

    fill("wrong", "A-new-long-phrase-9");

    await waitFor(() =>
      expect(screen.getByLabelText(/^Current password/).getAttribute("aria-invalid")).toBe("true"),
    );
    expect(screen.getByText("The current password is incorrect.")).toBeTruthy();
  });

  it("validates the confirmation locally", () => {
    renderWithI18n(<AccountView />);

    fill("Old-phrase-123", "A-new-long-phrase-9", "different");

    expect(screen.getByText("The passwords do not match.")).toBeTruthy();
    expect(changePassword).not.toHaveBeenCalled();
  });

  it("links back to this tab's company", () => {
    rememberCompany("22222222-2222-4222-8222-222222222222");
    renderWithI18n(<AccountView />);

    expect(screen.getByRole("link", { name: "Back to company" }).getAttribute("href")).toBe(
      "/c/22222222-2222-4222-8222-222222222222",
    );
  });
});
