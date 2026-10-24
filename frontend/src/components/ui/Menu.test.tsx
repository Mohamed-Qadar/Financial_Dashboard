import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Menu, MenuItem } from "./Menu";

function renderMenu(onSelect = vi.fn()) {
  render(
    <div>
      <Menu label="Actions" trigger="Open actions">
        <MenuItem onSelect={() => onSelect("one")}>One</MenuItem>
        <MenuItem onSelect={() => onSelect("two")} checked>
          Two
        </MenuItem>
        <MenuItem onSelect={() => onSelect("three")}>Three</MenuItem>
      </Menu>
      <button type="button">Outside</button>
    </div>,
  );
  return { button: screen.getByRole("button", { name: "Open actions" }), onSelect };
}

describe("Menu", () => {
  it("opens with the keyboard and focuses the checked item", () => {
    const { button } = renderMenu();
    expect(button.getAttribute("aria-expanded")).toBe("false");

    fireEvent.keyDown(button, { key: "ArrowDown" });

    expect(button.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByRole("menu", { name: "Actions" })).toBeTruthy();
    expect(document.activeElement?.textContent).toBe("Two");
  });

  it("moves with arrow keys, Home and End, wrapping around", () => {
    const { button } = renderMenu();
    fireEvent.click(button);
    const menu = screen.getByRole("menu");

    fireEvent.keyDown(menu, { key: "ArrowDown" });
    expect(document.activeElement?.textContent).toBe("Three");
    fireEvent.keyDown(menu, { key: "ArrowDown" });
    expect(document.activeElement?.textContent).toBe("One");
    fireEvent.keyDown(menu, { key: "End" });
    expect(document.activeElement?.textContent).toBe("Three");
    fireEvent.keyDown(menu, { key: "Home" });
    expect(document.activeElement?.textContent).toBe("One");
  });

  it("closes on Escape and returns focus to the button", () => {
    const { button } = renderMenu();
    fireEvent.click(button);

    fireEvent.keyDown(screen.getByRole("menu"), { key: "Escape" });

    expect(screen.queryByRole("menu")).toBeNull();
    expect(document.activeElement).toBe(button);
  });

  it("selects an item and closes", () => {
    const { button, onSelect } = renderMenu();
    fireEvent.click(button);

    fireEvent.click(screen.getByRole("menuitem", { name: "Three" }));

    expect(onSelect).toHaveBeenCalledWith("three");
    expect(screen.queryByRole("menu")).toBeNull();
  });

  it("closes when clicking outside", () => {
    const { button } = renderMenu();
    fireEvent.click(button);

    fireEvent.mouseDown(screen.getByRole("button", { name: "Outside" }));

    expect(screen.queryByRole("menu")).toBeNull();
  });

  it("marks the chosen option for assistive technology", () => {
    const { button } = renderMenu();
    fireEvent.click(button);

    expect(screen.getByRole("menuitemradio", { name: "Two" }).getAttribute("aria-checked")).toBe("true");
  });
});
