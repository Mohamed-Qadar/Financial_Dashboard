// @vitest-environment node
/** Project-wide frontend rules that must fail loudly when broken. */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";

import { afterEach, describe, expect, it, vi } from "vitest";

// The gallery's content is irrelevant here; only the page's environment guard is tested.
vi.mock("@/dev/UiPreview", () => ({ UiPreview: () => null }));

const SRC = join(process.cwd(), "src");

function sourceFiles(dir = SRC): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return sourceFiles(path);
    return /\.(ts|tsx)$/.test(name) ? [relative(SRC, path).split(sep).join("/")] : [];
  });
}

const isTest = (file: string) => /\.test\.(ts|tsx)$/.test(file) || file.startsWith("test/");
const isPreview = (file: string) => file.startsWith("dev/") || file.startsWith("app/ui-preview/");
const APP_FILES = sourceFiles().filter((file) => !isTest(file) && !isPreview(file));
const read = (file: string) => readFileSync(join(SRC, file), "utf8");

function offenders(files: string[], pattern: RegExp): string[] {
  return files.filter((file) => pattern.test(read(file)));
}

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("no fabricated data on production screens", () => {
  it("application code never imports preview data or the static (API-less) providers", () => {
    expect(offenders(APP_FILES, /@\/dev\/|previewData|StaticSessionProvider|StaticCompanyProvider/)).toEqual([
      // Defined (not used) here:
      "lib/company/CompanyProvider.tsx",
      "lib/session/SessionProvider.tsx",
    ]);
    const definitions = ["lib/company/CompanyProvider.tsx", "lib/session/SessionProvider.tsx"];
    for (const file of definitions) {
      expect(read(file)).not.toMatch(/@\/dev\/|previewData/);
    }
  });

  it("test fixtures are only used by tests", () => {
    expect(offenders(APP_FILES, /@\/test\/|test\/fixtures/)).toEqual([]);
  });

  it("the UI preview is a 404 outside development", async () => {
    const { default: UiPreviewPage } = await import("./app/ui-preview/page");
    vi.stubEnv("NODE_ENV", "production");
    expect(() => UiPreviewPage()).toThrow(/NEXT_HTTP_ERROR_FALLBACK;404/);
    vi.stubEnv("NODE_ENV", "test");
    expect(() => UiPreviewPage()).toThrow(/NEXT_HTTP_ERROR_FALLBACK;404/);
  });
});

describe("security conventions", () => {
  it("no raw HTML injection", () => {
    const nonTest = sourceFiles().filter((file) => !isTest(file));
    expect(offenders(nonTest, /dangerously[S]etInnerHTML/)).toEqual([]);
  });

  it("no inline style attributes (blocked by the Content Security Policy)", () => {
    const tsx = sourceFiles().filter((file) => file.endsWith(".tsx"));
    expect(offenders(tsx, /\sstyle=\{/)).toEqual([]);
  });

  it("browser storage only holds UI preferences, in the two modules that own them", () => {
    expect(offenders(APP_FILES, /localStorage|sessionStorage/)).toEqual([
      "lib/session/companyMemory.ts",
      "lib/usePersistentFlag.ts",
    ]);
  });

  it("API calls go through the client (CSRF, error handling), never raw fetch", () => {
    // lib/health.ts takes an injected fetch for the public, read-only readiness check.
    expect(offenders(APP_FILES, /\bfetch\(/)).toEqual(["lib/api/client.ts"]);
  });
});
