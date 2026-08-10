import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { SessionExpiredState } from "@eaios/ui";

import { SignInForm } from "../../components/portal/SignInForm";
import { NOT_INDEXED } from "../../lib/metadata";
import { getCurrentUser, SessionExpiredError, UnauthenticatedError } from "../../lib/portal-api";
import { sessionToken } from "../../lib/session";

/**
 * The employee portal's front door (spec 003 FR-006, FR-027).
 *
 * **The address has not changed.** Feature 002 reserved `/portal` and served a
 * "sign-in is not yet available" page there precisely so the anonymous boundary was
 * enforced and tested before the thing it guards arrived. Every header link on the
 * public site points here. FR-027 says the portal replaces that page's contents
 * *without changing the address*, and this is that replacement.
 *
 * Three states, decided before anything renders:
 *
 * * a live session → straight to the portal, because showing a sign-in form to
 *   somebody already signed in is a small lie about where they are;
 * * a cookie that the server no longer accepts → the **expired** state above the form,
 *   because "you were signed out" and "you have never been here" are different
 *   sentences (FR-005's edge case);
 * * nothing → the form.
 */
export const metadata: Metadata = {
  title: "Sign in",
  description: "Sign in to the NileTech employee portal.",
  ...NOT_INDEXED,
};

export default async function PortalSignInPage() {
  const hadSession = (await sessionToken()) !== null;
  let expired = false;

  if (hadSession) {
    try {
      await getCurrentUser();
      redirect("/portal/home");
    } catch (error) {
      if (isRedirect(error)) throw error;
      if (error instanceof SessionExpiredError) {
        expired = true;
      } else if (!(error instanceof UnauthenticatedError)) {
        // Rethrown for `error.tsx` to render. Falling through to the form meant an
        // outage looked exactly like a signed-out visitor: the person saw a sign-in
        // page, signed in, and failed again with no explanation. That is *error*
        // dressed as *unauthenticated*, the pair contracts/portal-routes.md §3 keeps
        // apart, and the shell was fixed for the same reason.
        throw error;
      }
      // `UnauthenticatedError` is not a failure here: it means there is no usable
      // credential, and the form below is exactly the right answer.
    }
  }

  return (
    <div style={{ maxWidth: "var(--content-narrow)" }}>
      <h1>Employee portal</h1>

      {expired ? (
        <SessionExpiredState>
          <p>
            You have been signed out to keep your account safe. Sign in again below to
            carry on.
          </p>
        </SessionExpiredState>
      ) : null}

      <p>
        Sign in with your work email address. If you cannot get in, your manager or the
        IT team can help.
      </p>

      <SignInForm />

      {/* A way out for someone who followed the header link by mistake. The holding
          page this replaced had one, and removing it would leave the sign-in form as
          a dead end for every visitor who is not an employee. */}
      <div className="eaios-actions">
        <Link href="/" className="eaios-button eaios-button--secondary">
          Back to the public site
        </Link>
      </div>
    </div>
  );
}

/**
 * Next signals a redirect by throwing, so the `catch` above would swallow it and turn
 * a successful sign-in into a silent fall-through to the form. Recognised and
 * rethrown rather than caught.
 */
function isRedirect(error: unknown): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    "digest" in error &&
    typeof (error as { digest?: unknown }).digest === "string" &&
    (error as { digest: string }).digest.startsWith("NEXT_REDIRECT")
  );
}
