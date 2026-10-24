import { notFound } from "next/navigation";

import { UiPreview } from "@/dev/UiPreview";

/**
 * Development-only component gallery. Any other environment (production build, tests,
 * `next start`) answers 404, so preview data can never appear on a production screen.
 */
export default function UiPreviewPage() {
  if (process.env.NODE_ENV !== "development") notFound();
  return <UiPreview />;
}
