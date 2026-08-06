"use client";

import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";

import { Button, Field } from "@eaios/ui";

type Status = "idle" | "submitting" | "failed" | "bounded";

/** Matches `ContactForm`: below this, a loading state reads as a flicker. */
const LOADING_DELAY_MS = 150;

/**
 * The one credential-accepting surface in this system (spec 003 FR-006, FR-022).
 *
 * It lives at the reserved portal address, never on the public site — spec 002 FR-048
 * forbids the eight content pages requiring, accepting, or storing any visitor
 * credential, and the check enforcing that must keep passing unchanged.
 *
 * **One message for every refusal.** The server answers unknown address, wrong
 * password, inactive user, missing credential, and a reached attempt bound
 * identically, and this form must not undo that by being helpful. There is no "we
 * don't recognise that address" branch here, and there must never be one — it would
 * turn a carefully generic API into an enumeration oracle at the last step.
 *
 * The only thing distinguished is a **malformed** address, which is a 422 and reveals
 * nothing: a string with no `@` cannot be anybody's account, so saying so tells an
 * attacker only what they already typed, and tells a person who mistyped something
 * genuinely useful.
 *
 * The token is never seen here. The form posts to the site's own route handler, which
 * moves it into an httpOnly cookie; this component receives `{ ok: true }`.
 */
export function SignInForm() {
  const router = useRouter();
  const formId = useId();
  const [status, setStatus] = useState<Status>("idle");
  const [message, setMessage] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [loadingVisible, setLoadingVisible] = useState(false);
  const summaryRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (status !== "submitting") {
      setLoadingVisible(false);
      return;
    }
    const timer = setTimeout(() => setLoadingVisible(true), LOADING_DELAY_MS);
    return () => clearTimeout(timer);
  }, [status]);

  // Focus moves to the failure so a keyboard or screen-reader user is taken to it
  // rather than left at the button wondering whether anything happened.
  useEffect(() => {
    if (status === "failed" || status === "bounded") summaryRef.current?.focus();
  }, [status]);

  const field = (name: string) => `${formId}-${name}`;

  async function onSubmit(event: React.FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const email = String(data.get(field("email")) ?? "").trim();
    const password = String(data.get(field("password")) ?? "");

    const found: Record<string, string> = {};
    if (!email) found.email = "Please enter your work email address.";
    if (!password) found.password = "Please enter your password.";
    if (Object.keys(found).length) {
      setFieldErrors(found);
      setStatus("failed");
      setMessage("Please complete both fields.");
      return;
    }

    setFieldErrors({});
    setStatus("submitting");

    let response: Response;
    try {
      response = await fetch("/portal/api/login", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
    } catch {
      setStatus("failed");
      setMessage("We could not reach our systems just now. Please try again.");
      return;
    }

    if (response.ok) {
      // A full navigation rather than a client transition: the server components on
      // the other side read the cookie this request just set, and only a real request
      // carries it.
      router.push("/portal/home");
      router.refresh();
      return;
    }

    if (response.status === 422) {
      setFieldErrors({ email: "That does not look like an email address." });
      setStatus("failed");
      setMessage("Please check the address and try again.");
      return;
    }

    // Everything else — including a reached attempt bound — gets the same sentence.
    setStatus("failed");
    setMessage("Those sign-in details were not accepted.");
  }

  const busy = status === "submitting";

  return (
    <form onSubmit={onSubmit} noValidate>
      <div
        ref={summaryRef}
        tabIndex={-1}
        role="alert"
        aria-live="assertive"
        className={message ? "eaios-state eaios-state--error" : undefined}
      >
        {message ? <p className="eaios-state__title">{message}</p> : null}
      </div>

      <Field
        id={field("email")}
        label="Work email address"
        type="email"
        autoComplete="username"
        required
        disabled={busy}
        error={fieldErrors.email}
      />

      <Field
        id={field("password")}
        label="Password"
        type="password"
        autoComplete="current-password"
        required
        disabled={busy}
        error={fieldErrors.password}
      />

      <div className="eaios-actions">
        <Button type="submit" disabled={busy}>
          {loadingVisible ? "Signing in…" : "Sign in"}
        </Button>
      </div>
    </form>
  );
}
