import Link from "next/link";

import { Icon } from "./ui/Icon";

export function Brand({ name, href = "/", compact = false }: { name: string; href?: string; compact?: boolean }) {
  return (
    <Link href={href} className="brand">
      <span className="brand-mark">
        <Icon name="layers" size={18} />
      </span>
      <span className={compact ? "visually-hidden" : undefined}>{name}</span>
    </Link>
  );
}
