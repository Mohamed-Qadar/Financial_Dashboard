import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

/** jsdom has no matchMedia; tests choose the viewport with `setViewport`. */
let desktop = true;
const listeners = new Set<() => void>();

export function setViewport(kind: "desktop" | "mobile") {
  desktop = kind === "desktop";
  listeners.forEach((listener) => listener());
}

if (typeof window !== "undefined") {
  window.matchMedia = (query: string) =>
    ({
      get matches() {
        return query.includes("min-width: 1024px") ? desktop : false;
      },
      media: query,
      onchange: null,
      addEventListener: (_: string, listener: () => void) => {
        listeners.add(listener);
      },
      removeEventListener: (_: string, listener: () => void) => {
        listeners.delete(listener);
      },
      addListener: () => undefined,
      removeListener: () => undefined,
      dispatchEvent: () => false,
    }) as unknown as MediaQueryList;
}

afterEach(() => {
  cleanup();
  setViewport("desktop");
  if (typeof window !== "undefined") {
    localStorage.clear();
    sessionStorage.clear();
  }
});
