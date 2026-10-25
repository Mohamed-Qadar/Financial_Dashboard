import { monogramLetters, monogramTone } from "@/lib/format";

/** Initials badge for a company or business, coloured from its id (decorative). */
export function Monogram({ id, name, size = "md" }: { id: string; name: string; size?: "sm" | "md" | "lg" | "xl" }) {
  return (
    <span className="ui-monogram" data-tone={monogramTone(id)} data-size={size} aria-hidden="true">
      {monogramLetters(name)}
    </span>
  );
}
