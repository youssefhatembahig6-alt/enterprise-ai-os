import type { ReactNode } from "react";

type Props = {
  tone: "error" | "success";
  title: string;
  children?: ReactNode;
};

/**
 * `role="alert"` for errors (interrupts) and `role="status"` for success (polite).
 * FR-038 requires dynamic changes to reach assistive technology; the distinction
 * matters because a success message that interrupts is as wrong as an error that
 * stays silent.
 */
export function Alert({ tone, title, children }: Props) {
  return (
    <div
      className={`eaios-state eaios-state--${tone}`}
      role={tone === "error" ? "alert" : "status"}
    >
      <p className="eaios-state__title">{title}</p>
      {children}
    </div>
  );
}
