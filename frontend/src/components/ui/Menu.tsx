"use client";

import Link from "next/link";
import {
  createContext,
  type KeyboardEvent,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useId,
  useRef,
  useState,
} from "react";

import { Icon, type IconName } from "./Icon";

const MenuContext = createContext<{ close: (returnFocus?: boolean) => void } | null>(null);

function items(list: HTMLElement | null): HTMLElement[] {
  if (!list) return [];
  return Array.from(list.querySelectorAll<HTMLElement>("[data-menu-item]:not([aria-disabled='true'])"));
}

/**
 * Menu button (WAI-ARIA menu pattern): Enter/Space/ArrowDown opens and focuses the selected
 * or first item; ArrowUp/ArrowDown/Home/End move; Escape closes and returns focus to the
 * button; Tab or a click outside closes.
 */
export function Menu({
  label,
  trigger,
  children,
  align = "end",
  onOpen,
  buttonClassName = "ui-menu-button",
}: {
  label: string;
  trigger: ReactNode;
  children: ReactNode;
  align?: "start" | "end";
  onOpen?: () => void;
  buttonClassName?: string;
}) {
  const [open, setOpen] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const id = useId();

  const close = useCallback((returnFocus = true) => {
    setOpen(false);
    if (returnFocus) buttonRef.current?.focus();
  }, []);

  useEffect(() => {
    if (!open) return;
    const all = items(listRef.current);
    const checked = all.find((item) => item.getAttribute("aria-checked") === "true");
    (checked ?? all[0])?.focus();
    function onPointerDown(event: MouseEvent) {
      if (!rootRef.current?.contains(event.target as Node)) close(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, [open, close]);

  function openMenu() {
    onOpen?.();
    setOpen(true);
  }

  function onButtonKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      openMenu();
    }
  }

  function onListKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const all = items(listRef.current);
    const index = all.indexOf(document.activeElement as HTMLElement);
    const focusAt = (position: number) => all[(position + all.length) % all.length]?.focus();
    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        focusAt(index + 1);
        break;
      case "ArrowUp":
        event.preventDefault();
        focusAt(index - 1);
        break;
      case "Home":
        event.preventDefault();
        focusAt(0);
        break;
      case "End":
        event.preventDefault();
        focusAt(all.length - 1);
        break;
      case "Escape":
        event.preventDefault();
        close();
        break;
      case "Tab":
        close(false);
        break;
    }
  }

  return (
    <MenuContext.Provider value={{ close }}>
      <div className="ui-menu" ref={rootRef}>
        <button
          ref={buttonRef}
          type="button"
          className={buttonClassName}
          aria-haspopup="menu"
          aria-expanded={open}
          aria-controls={open ? id : undefined}
          onClick={() => (open ? close(false) : openMenu())}
          onKeyDown={onButtonKeyDown}
        >
          {trigger}
        </button>
        {open ? (
          <div
            ref={listRef}
            id={id}
            role="menu"
            aria-label={label}
            className="ui-menu-list"
            data-align={align}
            onKeyDown={onListKeyDown}
          >
            {children}
          </div>
        ) : null}
      </div>
    </MenuContext.Provider>
  );
}

function useMenu() {
  const value = useContext(MenuContext);
  if (!value) throw new Error("Menu items must be inside <Menu>.");
  return value;
}

export function MenuItem({
  children,
  onSelect,
  icon,
  checked,
  disabled,
}: {
  children: ReactNode;
  onSelect: () => void;
  icon?: IconName;
  /** For a choice among options (e.g. the active company). */
  checked?: boolean;
  disabled?: boolean;
}) {
  const { close } = useMenu();
  return (
    <button
      type="button"
      role={checked === undefined ? "menuitem" : "menuitemradio"}
      aria-checked={checked}
      aria-disabled={disabled || undefined}
      tabIndex={-1}
      data-menu-item
      className="ui-menu-item"
      onClick={() => {
        if (disabled) return;
        close(false);
        onSelect();
      }}
    >
      {icon ? <Icon name={icon} size={16} /> : null}
      <span className="ui-menu-item-label">{children}</span>
      {checked ? <Icon name="check" size={16} /> : null}
    </button>
  );
}

export function MenuLink({ href, icon, children }: { href: string; icon?: IconName; children: ReactNode }) {
  const { close } = useMenu();
  return (
    <Link
      href={href}
      role="menuitem"
      tabIndex={-1}
      data-menu-item
      className="ui-menu-item"
      onClick={() => close(false)}
    >
      {icon ? <Icon name={icon} size={16} /> : null}
      <span className="ui-menu-item-label">{children}</span>
    </Link>
  );
}

export function MenuGroup({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div role="group" aria-label={label} className="ui-menu-group">
      <p className="ui-menu-group-label" aria-hidden="true">
        {label}
      </p>
      {children}
    </div>
  );
}

/** Non-interactive text inside a menu (e.g. who is signed in, loading, errors). */
export function MenuNote({ children }: { children: ReactNode }) {
  return (
    <div className="ui-menu-note" role="none">
      {children}
    </div>
  );
}
