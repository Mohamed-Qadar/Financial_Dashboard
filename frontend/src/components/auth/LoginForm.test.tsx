import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api/errors";
import { renderWithI18n } from "@/test/i18n";

import { LoginForm } from "./LoginForm";

const replace = vi.fn();
const refresh = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, refresh, push: vi.fn() }),
}));

const login = vi.fn();
vi.mock("@/lib/api/endpoints", () => ({
  auth: { login: (...args: unknown[]) => login(...args) },
}));

function fill(email: string, password: string) {
  fireEvent.change(screen.getByLabelText(/Email address/), { target: { value: email } });
  fireEvent.change(screen.getByLabelText(/^Password/), { target: { value: password } });
}

beforeEach(() => vi.clearAllMocks());

describe("LoginForm", () => {
  it("signs in and continues to the requested page", async () => {
    login.mockResolvedValue({ id: "u" });
    renderWithI18n(<LoginForm next="/c/abc" expired={false} />);

    fill("  Hodan@Example.com ", "secret-phrase");
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/c/abc"));
    expect(login).toHaveBeenCalledWith("Hodan@Example.com", "secret-phrase");
  });

  it("requires both fields before calling the API", () => {
    renderWithI18n(<LoginForm next="/select-company" expired={false} />);

    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(login).not.toHaveBeenCalled();
    expect(screen.getAllByText("Required")).toHaveLength(2);
    expect(screen.getByLabelText(/Email address/).getAttribute("aria-invalid")).toBe("true");
  });

  it("shows the same generic message for every credential failure and clears the password", async () => {
    login.mockRejectedValue(new ApiError(400, "invalid_credentials", "Invalid email or password."));
    renderWithI18n(<LoginForm next="/select-company" expired={false} />);

    fill("hodan@example.com", "wrong");
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect((await screen.findByRole("alert")).textContent).toContain("Incorrect email or password.");
    expect((screen.getByLabelText(/^Password/) as HTMLInputElement).value).toBe("");
    expect(replace).not.toHaveBeenCalled();
  });

  it("tells a rate-limited user how long to wait, in Somali", async () => {
    login.mockRejectedValue(new ApiError(429, "throttled", "x", undefined, undefined, 120));
    renderWithI18n(<LoginForm next="/select-company" expired={false} />, "so");

    fireEvent.change(screen.getByLabelText(/Ciwaanka iimaylka/), { target: { value: "a@b.so" } });
    fireEvent.change(screen.getByLabelText(/^Erayga sirta ah/), { target: { value: "x" } });
    fireEvent.click(screen.getByRole("button", { name: "Soo gal" }));

    expect((await screen.findByRole("alert")).textContent).toContain("2 daqiiqo");
  });

  it("explains an ended session", () => {
    renderWithI18n(<LoginForm next="/select-company" expired />);

    expect(screen.getByRole("status").textContent).toContain("Your session has ended");
  });

  it("toggles password visibility with an accessible button", () => {
    renderWithI18n(<LoginForm next="/select-company" expired={false} />);
    const input = screen.getByLabelText(/^Password/) as HTMLInputElement;
    const toggle = screen.getByRole("button", { name: "Show password" });

    fireEvent.click(toggle);

    expect(input.type).toBe("text");
    expect(screen.getByRole("button", { name: "Hide password" }).getAttribute("aria-pressed")).toBe("true");
  });
});
