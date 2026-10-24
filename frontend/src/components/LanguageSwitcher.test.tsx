import { fireEvent, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithI18n } from "@/test/i18n";

import { LanguageSwitcher } from "./LanguageSwitcher";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), refresh, push: vi.fn() }),
}));

beforeEach(() => {
  vi.clearAllMocks();
  document.cookie = "erp_lang=; Max-Age=0; Path=/";
});

describe("LanguageSwitcher", () => {
  it("marks the current language and switches with a cookie + server refresh", () => {
    renderWithI18n(<LanguageSwitcher />, "so");

    const group = screen.getByRole("group", { name: "Luqadda" });
    expect(group).toBeTruthy();
    expect(screen.getByRole("button", { name: "Soomaali" }).getAttribute("aria-pressed")).toBe("true");

    fireEvent.click(screen.getByRole("button", { name: "English" }));

    expect(document.cookie).toContain("erp_lang=en");
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it("does nothing when the current language is chosen again", () => {
    renderWithI18n(<LanguageSwitcher />, "en");

    fireEvent.click(screen.getByRole("button", { name: "English" }));

    expect(refresh).not.toHaveBeenCalled();
  });
});
