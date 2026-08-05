import type { ButtonHTMLAttributes, ReactNode } from "react";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary";
  children: ReactNode;
};

/** Minimum target size and focus visibility come from the token layer, so a
 *  caller cannot opt out of either (FR-033, FR-037). */
export function Button({ variant = "primary", className, children, ...rest }: Props) {
  const classes = [
    "eaios-button",
    variant === "secondary" ? "eaios-button--secondary" : "",
    className ?? "",
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <button className={classes} {...rest}>
      {children}
    </button>
  );
}
