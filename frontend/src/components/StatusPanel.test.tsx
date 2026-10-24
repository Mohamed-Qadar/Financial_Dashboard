import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatusPanel } from "./StatusPanel";

describe("StatusPanel", () => {
  it("shows both services as operational", () => {
    render(<StatusPanel status={{ api: "ok", database: "ok" }} />);

    expect(screen.getByRole("heading", { name: "System status" })).toBeTruthy();
    expect(screen.getAllByText("Operational")).toHaveLength(2);
  });

  it("marks a failing database as a problem", () => {
    render(<StatusPanel status={{ api: "ok", database: "unavailable" }} />);

    const badge = screen.getByText("Unavailable");
    expect(badge.className).toContain("badge-problem");
  });
});
