"use client";

import { useEffect, useId, useRef, useState } from "react";

import { Alert, Button, Field } from "@eaios/ui";

import { submitContact } from "../lib/api";

type Status = "idle" | "submitting" | "sent" | "failed" | "bounded";

/**
 * FR-027a — the loading state appears only after 150ms.
 *
 * The requirement names a number so SC-014 has something to test against, and the
 * reason for the delay is what a fast response looks like without it: the button
 * flickers to "Sending…" and back within one frame, which reads as a glitch rather
 * than as progress. On a local stack the round trip is well under this, so the
 * loading state correctly never appears at all.
 *
 * The *disabled* state is not delayed. That is a duplicate-submission guard
 * (FR-022), not a loading indicator, and it has to take effect on the first click.
 */
const LOADING_DELAY_MS = 150;

/**
 * The site's only write path (spec 002 FR-019 – FR-024c).
 *
 * The client rules here are a *convenience* — they tell the visitor sooner. The
 * server is the control (FR-020), and `tests/integration/test_contact_submission.py`
 * submits directly, bypassing this file entirely, to prove that.
 *
 * The one client-fetched region in this feature, so it is also the only place a
 * loading state can genuinely occur (FR-025 as amended).
 */
export function ContactForm() {
  const formId = useId();
  const [status, setStatus] = useState<Status>("idle");
  const [errors, setErrors] = useState<Record<string, string>>({});
  /** The server's own sentence when the per-address bound is reached (FR-024d). */
  const [boundedMessage, setBoundedMessage] = useState("");
  const [loadingVisible, setLoadingVisible] = useState(false);
  const formRef = useRef<HTMLFormElement>(null);
  const summaryRef = useRef<HTMLDivElement>(null);

  // Held in an effect rather than in the submit handler so the timer is cleaned up
  // if the component unmounts mid-flight — a pending `setState` on an unmounted
  // form is the classic way this pattern leaks.
  useEffect(() => {
    if (status !== "submitting") {
      setLoadingVisible(false);
      return;
    }
    const timer = setTimeout(() => setLoadingVisible(true), LOADING_DELAY_MS);
    return () => clearTimeout(timer);
  }, [status]);

  const field = (name: string) => `${formId}-${name}`;

  function validate(values: Record<string, string>): Record<string, string> {
    const found: Record<string, string> = {};
    if (!values.sender_name?.trim()) found.sender_name = "Please tell us your name.";
    if (!values.sender_email?.trim()) {
      found.sender_email = "Please give us an email address so we can reply.";
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(values.sender_email.trim())) {
      found.sender_email = "That does not look like an email address. Please check it.";
    }
    if (!values.subject?.trim()) found.subject = "Please add a subject.";
    if (!values.message?.trim()) found.message = "Please write your message.";
    return found;
  }

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const values = Object.fromEntries(
      ["sender_name", "sender_email", "subject", "message"].map((key) => [
        key,
        String(data.get(key) ?? ""),
      ]),
    );

    const found = validate(values);
    if (Object.keys(found).length > 0) {
      // Nothing the visitor typed is cleared (FR-021) — the form is uncontrolled,
      // so the DOM keeps their input and only the messages change.
      setErrors(found);
      setStatus("idle");
      summaryRef.current?.focus();
      return;
    }

    setErrors({});
    setStatus("submitting");

    try {
      const result = await submitContact({
        sender_name: values.sender_name!.trim(),
        sender_email: values.sender_email!.trim(),
        subject: values.subject!.trim(),
        message: values.message!.trim(),
      });

      if (result.ok) {
        setStatus("sent");
        formRef.current?.reset();
        return;
      }

      if (result.kind === "bounded") {
        // Not an error state and not a success: the message was understood and
        // deliberately refused. Nothing the visitor typed is cleared — they should
        // be able to send it later without retyping it (the same reasoning FR-021
        // applies to validation failures).
        setBoundedMessage(result.message);
        setStatus("bounded");
        summaryRef.current?.focus();
        return;
      }

      setErrors(Object.fromEntries(result.errors.map((e) => [e.field, e.message])));
      setStatus("idle");
      summaryRef.current?.focus();
    } catch {
      // The visitor is never told a failed submission succeeded (US4/AC5).
      setStatus("failed");
    }
  }

  if (status === "sent") {
    return (
      <Alert tone="success" title="Thank you — your message has been received">
        <p>
          We read everything that comes in and will reply to the address you gave us.
        </p>
        <Button variant="secondary" type="button" onClick={() => setStatus("idle")}>
          Send another message
        </Button>
      </Alert>
    );
  }

  const errorCount = Object.keys(errors).length;

  return (
    <form ref={formRef} onSubmit={onSubmit} noValidate aria-label="Contact form">
      {/* Focused on failure so a keyboard or screen-reader user is taken to the
          problem rather than left to hunt for it. */}
      <div ref={summaryRef} tabIndex={-1}>
        {errorCount > 0 ? (
          <Alert tone="error" title="Some details need your attention">
            <p>Please correct the {errorCount === 1 ? "field" : "fields"} marked below.</p>
          </Alert>
        ) : null}

        {status === "bounded" ? (
          <Alert tone="error" title="We have your recent messages">
            <p>{boundedMessage}</p>
          </Alert>
        ) : null}

        {status === "failed" ? (
          <Alert tone="error" title="Your message was not sent">
            <p>
              We could not reach our systems just now. Nothing was saved — please try
              again in a moment.
            </p>
          </Alert>
        ) : null}
      </div>

      <Field
        id={field("sender_name")}
        name="sender_name"
        label="Your name"
        required
        maxLength={120}
        autoComplete="name"
        error={errors.sender_name}
      />

      <Field
        id={field("sender_email")}
        name="sender_email"
        label="Email address"
        type="email"
        required
        maxLength={254}
        autoComplete="email"
        hint="We will only use this to reply to you."
        error={errors.sender_email}
      />

      <Field
        id={field("subject")}
        name="subject"
        label="Subject"
        required
        maxLength={150}
        error={errors.subject}
      />

      <Field
        id={field("message")}
        name="message"
        label="Message"
        multiline
        required
        maxLength={4000}
        error={errors.message}
      />

      {/* FR-024a — what we collect and how long we keep it, at the point of
          collection. Not buried in a policy page nobody opens. */}
      <p className="eaios-field__hint">
        We store your name, email address, and message so we can reply, and delete them
        after 90 days. We do not share them with anyone else.
      </p>

            {/* Left enabled while bounded, deliberately. T113 established that an
          interface which reports a problem and stays disabled has substituted one
          dead end for another; a visitor who tries again simply sees the same
          sentence, which is honest and costs the server a refusal it was going to
          issue anyway. */}
      <Button type="submit" disabled={status === "submitting"}>
        {loadingVisible ? "Sending…" : "Send message"}
      </Button>

      {/* Announced rather than shown only as a disabled button (FR-038). Delayed
          with the visual state: announcing "sending" and "sent" within 150ms of each
          other is noise to a screen-reader user, not information. */}
      <p role="status" className="sr-only">
        {loadingVisible ? "Sending your message" : ""}
      </p>
    </form>
  );
}
