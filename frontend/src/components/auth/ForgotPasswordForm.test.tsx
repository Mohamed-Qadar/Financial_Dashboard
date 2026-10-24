import { fireEvent, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api/errors";
import { renderWithI18n } from "@/test/i18n";

import { ForgotPasswordForm } from "./ForgotPasswordForm";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }),
}));

const requestPasswordReset = vi.fn();
vi.mock("@/lib/api/endpoints", () => ({
  auth: { requestPasswordReset: (...args: unknown[]) => requestPasswordReset(...args) },
}));

beforeEach(() => vi.clearAllMocks());

function submit(email: string) {
  fireEvent.change(screen.getByLabelText(/Email address/), { target: { value: email } });
  fireEvent.click(screen.getByRole("button", { name: "Send reset link" }));
}

describe("ForgotPasswordForm", () => {
  it("shows the same confirmation whether or not the account exists", async () => {
    requestPasswordReset.mockResolvedValue(undefined); // the backend always answers 202
    renderWithI18n(<ForgotPasswordForm />);

    submit("anyone@example.com");

    expect(await screen.findByRole("heading", { name: "Check your email" })).toBeTruthy();
    expect(screen.getByRole("status").textContent).toContain("If an account exists");
    expect(document.body.textContent).not.toContain("anyone@example.com");
  });

  it("reports rate limiting", async () => {
    requestPasswordReset.mockRejectedValue(new ApiError(429, "throttled", "x"));
    renderWithI18n(<ForgotPasswordForm />);

    submit("anyone@example.com");

    expect((await screen.findByRole("alert")).textContent).toContain("Too many attempts");
  });
});
