import Link from "next/link";

import { Icon } from "./ui/Icon";

export function Brand({
  name,
  tagline,
  href = "/",
  compact = false,
}: {
  name: string;
  tagline?: string;
  href?: string;
  compact?: boolean;
}) {
  return (
    <Link href={href} className="brand" title={compact ? name : undefined}>
      <span className="brand-mark">
        <Icon name="layers" size={18} />
      </span>
      <span className={compact ? "visually-hidden" : "brand-text"}>
        <span className="brand-name">{name}</span>
        {tagline ? <span className="brand-tagline">{tagline}</span> : null}
      </span>
    </Link>
  );
}
