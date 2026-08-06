/**
 * The sign-in form (spec 003 FR-006, FR-022, FR-029).
 *
 * The one credential-accepting surface in the system, so what it *does not* say
 * matters as much as what it does. The server answers every sign-in refusal
 * identically on purpose (FR-022); a form that helpfully distinguished them would
 * hand back the enumeration oracle the API was written to withhold.
 *
 * The server is the control. `tests/security/test_login_enumeration.py` proves the
 * refusals are indistinguishable at the source, bypassing this file entirely — a
 * browser-driven test of a message proves only what the browser was told to render.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SignInForm } from "../components/portal/SignInForm";

const push = vi.fn();
const refresh = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh }),
}));

function respondWith(status: number, body: unknown = {}) {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        ({ ok: status >= 200 && status < 300, status, json: async () => body }) as Response,
    ),
  );
}

beforeEach(() => {
  push.mockClear();
  refresh.mockClear();
  respondWith(200, { ok: true });
});

afterEach(() => vi.restoreAllMocks());

describe("the form is usable", () => {
  it("labels both controls", () => {
    render(<SignInForm />);
    expect(screen.getByLabelText(/work email address/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
  });

  it("marks the password field as a password", () => {
    render(<SignInForm />);
    expect(screen.getByLabelText(/password/i)).toHaveAttribute("type", "password");
  });

  it("offers the browser the right autocomplete hints", () => {
    // Not decoration: without these a password manager cannot fill the form, and the
    // people most likely to have a strong unique password are the ones using one.
    render(<SignInForm />);
    expect(screen.getByLabelText(/work email address/i)).toHaveAttribute(
      "autocomplete",
      "username",
    );
    expect(screen.getByLabelText(/password/i)).toHaveAttribute(
      "autocomplete",
      "current-password",
    );
  });
});

describe("client-side validation is a convenience", () => {
  it("names each empty field without contacting the server", async () => {
    const user = userEvent.setup();
    render(<SignInForm />);
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByText(/please enter your work email address/i)).toBeInTheDocument();
    expect(screen.getByText(/please enter your password/i)).toBeInTheDocument();
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it("associates each message with its control", async () => {
    const user = userEvent.setup();
    render(<SignInForm />);
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    // `aria-invalid` plus `aria-describedby` is what makes the message *available*
    // rather than merely visible — the distinction `Field` exists to enforce.
    await waitFor(() =>
      expect(screen.getByLabelText(/work email address/i)).toHaveAttribute(
        "aria-invalid",
        "true",
      ),
    );
    expect(screen.getByLabelText(/work email address/i)).toHaveAttribute("aria-describedby");
  });
});

describe("every refusal says the same thing", () => {
  const causes = [
    ["an unknown address", 401],
    ["a wrong password", 401],
    ["a locked-out account", 401],
  ] as const;

  it.each(causes)("shows one generic message for %s", async (_cause, status) => {
    respondWith(status, { title: "Not signed in", status, detail: "irrelevant" });
    const user = userEvent.setup();
    render(<SignInForm />);

    await user.type(screen.getByLabelText(/work email address/i), "someone@niletech.example");
    await user.type(screen.getByLabelText(/password/i), "whatever");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(
      await screen.findByText(/those sign-in details were not accepted/i),
    ).toBeInTheDocument();
  });

  it("never suggests whether the account exists", async () => {
    respondWith(401, { title: "Not signed in", status: 401, detail: "x" });
    const user = userEvent.setup();
    const { container } = render(<SignInForm />);

    await user.type(screen.getByLabelText(/work email address/i), "nobody@niletech.example");
    await user.type(screen.getByLabelText(/password/i), "whatever");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await screen.findByText(/those sign-in details were not accepted/i);
    const text = (container.textContent ?? "").toLowerCase();
    for (const leak of ["no such", "not found", "exists", "unknown", "incorrect password"]) {
      expect(text).not.toContain(leak);
    }
  });

  it("does not echo the address back", async () => {
    // A refusal repeating the address is a small thing that makes a phishing page's
    // job easier and tells a shoulder-surfer who was being tried.
    respondWith(401, { title: "Not signed in", status: 401, detail: "x" });
    const user = userEvent.setup();
    const { container } = render(<SignInForm />);

    await user.type(screen.getByLabelText(/work email address/i), "victim@niletech.example");
    await user.type(screen.getByLabelText(/password/i), "whatever");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await screen.findByText(/those sign-in details were not accepted/i);
    const alert = container.querySelector('[role="alert"]');
    expect(alert?.textContent ?? "").not.toContain("victim@niletech.example");
  });
});

describe("a malformed address is treated differently, and that is correct", () => {
  it("says the address looks wrong", async () => {
    // 422, not 401. A string with no `@` cannot be anybody's account, so saying so
    // reveals nothing about which accounts exist — and helps the person who mistyped.
    respondWith(422, {});
    const user = userEvent.setup();
    render(<SignInForm />);

    await user.type(screen.getByLabelText(/work email address/i), "not-an-address");
    await user.type(screen.getByLabelText(/password/i), "whatever");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(
      await screen.findByText(/that does not look like an email address/i),
    ).toBeInTheDocument();
  });
});

describe("success", () => {
  it("navigates into the portal", async () => {
    const user = userEvent.setup();
    render(<SignInForm />);

    await user.type(screen.getByLabelText(/work email address/i), "someone@niletech.example");
    await user.type(screen.getByLabelText(/password/i), "correct");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => expect(push).toHaveBeenCalledWith("/portal/home"));
  });

  it("posts to the site's own route handler, never to the API", async () => {
    // The whole point of research R3: the browser must not talk to the API directly,
    // so the token can be moved into an httpOnly cookie without ever being readable.
    const user = userEvent.setup();
    render(<SignInForm />);

    await user.type(screen.getByLabelText(/work email address/i), "someone@niletech.example");
    await user.type(screen.getByLabelText(/password/i), "correct");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    const call = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(call?.[0]).toBe("/portal/api/login");
  });
});

describe("network failure", () => {
  it("says we could not be reached, not that the credentials were wrong", async () => {
    // The distinction feature 002 had to learn: a refusal the interface cannot tell
    // from an outage is one it will describe wrongly.
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("network down");
      }),
    );
    const user = userEvent.setup();
    render(<SignInForm />);

    await user.type(screen.getByLabelText(/work email address/i), "someone@niletech.example");
    await user.type(screen.getByLabelText(/password/i), "correct");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByText(/could not reach our systems/i)).toBeInTheDocument();
  });
});
