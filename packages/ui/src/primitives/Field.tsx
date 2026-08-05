import type { InputHTMLAttributes, ReactNode, TextareaHTMLAttributes } from "react";

type Common = {
  id: string;
  label: string;
  /** Rendered and announced. FR-021 requires the message to reach assistive
   *  technology as well as the eye, which `aria-describedby` plus `role="alert"`
   *  achieves without a live region wrapping the whole form. */
  error?: string | undefined;
  hint?: string | undefined;
  required?: boolean;
};

type InputProps = Common & { multiline?: false } & InputHTMLAttributes<HTMLInputElement>;
type AreaProps = Common & { multiline: true } & TextareaHTMLAttributes<HTMLTextAreaElement>;

/**
 * A labelled control with its error programmatically associated.
 *
 * The association is the part that matters. A message rendered near a field is
 * visible; a message referenced by `aria-describedby` and marked invalid is
 * *available* — those are different things, and only the second satisfies FR-021.
 */
export function Field(props: InputProps | AreaProps): ReactNode {
  const { id, label, error, hint, required, multiline, ...rest } = props as AreaProps;

  const errorId = `${id}-error`;
  const hintId = `${id}-hint`;
  const describedBy = [error ? errorId : null, hint ? hintId : null]
    .filter(Boolean)
    .join(" ");

  const shared = {
    id,
    name: id,
    className: "eaios-field__control",
    "aria-invalid": error ? true : undefined,
    "aria-describedby": describedBy || undefined,
    "aria-required": required || undefined,
  } as const;

  return (
    <div className="eaios-field">
      <label className="eaios-field__label" htmlFor={id}>
        {label}
        {required ? (
          <span className="eaios-field__required" aria-hidden="true">
            *
          </span>
        ) : null}
      </label>

      {hint ? (
        <span className="eaios-field__hint" id={hintId}>
          {hint}
        </span>
      ) : null}

      {multiline ? (
        <textarea rows={6} {...shared} {...(rest as TextareaHTMLAttributes<HTMLTextAreaElement>)} />
      ) : (
        <input {...shared} {...(rest as InputHTMLAttributes<HTMLInputElement>)} />
      )}

      {error ? (
        <span className="eaios-field__error" id={errorId} role="alert">
          {error}
        </span>
      ) : null}
    </div>
  );
}
