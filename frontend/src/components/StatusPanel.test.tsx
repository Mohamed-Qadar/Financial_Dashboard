import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { getMessages } from "@/lib/i18n";

import { StatusPanel } from "./StatusPanel";

const en = getMessages("en").status;
const so = getMessages("so").status;

describe("StatusPanel", () => {
  it("shows both services as operational", () => {
    render(<StatusPanel status={{ api: "ok", database: "ok" }} messages={en} />);

    expect(screen.getByRole("heading", { name: "System status" })).toBeTruthy();
    expect(screen.getAllByText("Operational")).toHaveLength(2);
  });

  it("marks a failing database as a problem with text, not only colour", () => {
    render(<StatusPanel status={{ api: "ok", database: "unavailable" }} messages={en} />);

    const badge = screen.getByText("Unavailable");
    expect(badge.getAttribute("data-tone")).toBe("danger");
  });

  it("renders in Somali", () => {
    render(<StatusPanel status={{ api: "ok", database: "ok" }} messages={so} />);

    expect(screen.getByRole("heading", { name: "Xaaladda nidaamka" })).toBeTruthy();
    expect(screen.getAllByText("Wuu shaqaynayaa")).toHaveLength(2);
  });
});
