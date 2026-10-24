import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api/errors";
import { renderWithI18n } from "@/test/i18n";

import { ResetPasswordForm } from "./ResetPasswordForm";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }),
}));

const confirmPasswordReset = vi.fn();
vi.mock("@/lib/api/endpoints", () => ({
  auth: { confirmPasswordReset: (...args: unknown[]) => confirmPasswordReset(...args) },
}));

function openLink(query: string) {
  window.history.replaceState(null, "", `/reset-password${query}`);
}

function submitPasswords(password: string, confirmation: string) {
  fireEvent.change(screen.getByLabelText(/^New password/), { target: { value: password } });
  fireEvent.change(screen.getByLabelText(/^Confirm new password/), {
    target: { value: confirmation },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save new password" }));
}

beforeEach(() => vi.clearAllMocks());

describe("ResetPasswordForm", () => {
  it("takes uid and token from the link and removes them from the address bar", async () => {
    openLink("?uid=MTIz&token=abc-secret-token");
    confirmPasswordReset.mockResolvedValue(undefined);
    renderWithI18n(<ResetPasswordForm />);

    await screen.findByRole("heading", { name: "Choose a new password" });
    expect(window.location.search).toBe("");
    expect(document.body.textContent).not.toContain("abc-secret-token");

    submitPasswords("A-long-new-phrase-1", "A-long-new-phrase-1");

    expect(await screen.findByRole("heading", { name: "Password changed" })).toBeTruthy();
    expect(confirmPasswordReset).toHaveBeenCalledWith("MTIz", "abc-secret-token", "A-long-new-phrase-1");
  });

  it("checks that both passwords match before calling the API", async () => {
    openLink("?uid=MTIz&token=t");
    renderWithI18n(<ResetPasswordForm />);
    await screen.findByRole("heading", { name: "Choose a new password" });

    submitPasswords("A-long-new-phrase-1", "different");

    expect(screen.getByText("The passwords do not match.")).toBeTruthy();
    expect(confirmPasswordReset).not.toHaveBeenCalled();
  });

  it.each(["", "?uid=MTIz", "?token=t", `?uid=MTIz&token=${"x".repeat(129)}`])(
    "treats the incomplete link %j as unusable",
    async (query) => {
      openLink(query);
      renderWithI18n(<ResetPasswordForm />);

      expect(await screen.findByRole("heading", { name: "This reset link cannot be used" })).toBeTruthy();
    },
  );

  it("shows the unusable-link page when the backend rejects the link", async () => {
    openLink("?uid=MTIz&token=used");
    confirmPasswordReset.mockRejectedValue(new ApiError(400, "invalid_reset_link", "x"));
    renderWithI18n(<ResetPasswordForm />);
    await screen.findByRole("heading", { name: "Choose a new password" });

    submitPasswords("A-long-new-phrase-1", "A-long-new-phrase-1");

    expect(await screen.findByRole("heading", { name: "This reset link cannot be used" })).toBeTruthy();
  });

  it("shows the backend's password rules next to the field", async () => {
    openLink("?uid=MTIz&token=t");
    confirmPasswordReset.mockRejectedValue(
      new ApiError(400, "validation_error", "Invalid input.", undefined, {
        new_password: ["This password is too common."],
      }),
    );
    renderWithI18n(<ResetPasswordForm />);
    await screen.findByRole("heading", { name: "Choose a new password" });

    submitPasswords("password1234", "password1234");

    await waitFor(() => expect(screen.getByText("This password is too common.")).toBeTruthy());
    expect(screen.getByLabelText(/^New password/).getAttribute("aria-invalid")).toBe("true");
  });
});
