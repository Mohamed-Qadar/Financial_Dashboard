import Link from "next/link";
import type { ButtonHTMLAttributes, ReactNode } from "react";

import { Icon, type IconName } from "./Icon";
import { Spinner } from "./Spinner";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "md" | "sm";

interface CommonProps {
  variant?: Variant;
  size?: Size;
  icon?: IconName;
  children: ReactNode;
}

export interface ButtonProps
  extends CommonProps,
    Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children"> {
  /** Shows a spinner, disables the button and announces it as busy. */
  loading?: boolean;
  /** Text shown while loading (e.g. "Signing in…"). */
  loadingText?: string;
}

export function Button({
  variant = "primary",
  size = "md",
  icon,
  loading = false,
  loadingText,
  children,
  type = "button",
  disabled,
  ...rest
}: ButtonProps) {
  return (
    <button
      {...rest}
      type={type}
      className="ui-button"
      data-variant={variant}
      data-size={size}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
    >
      {loading ? <Spinner /> : icon ? <Icon name={icon} size={16} /> : null}
      <span>{loading && loadingText ? loadingText : children}</span>
    </button>
  );
}

export function ButtonLink({
  href,
  variant = "secondary",
  size = "md",
  icon,
  children,
}: CommonProps & { href: string }) {
  return (
    <Link href={href} className="ui-button" data-variant={variant} data-size={size}>
      {icon ? <Icon name={icon} size={16} /> : null}
      <span>{children}</span>
    </Link>
  );
}
