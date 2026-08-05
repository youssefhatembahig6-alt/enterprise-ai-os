/**
 * Contact form behaviour (spec 002 FR-021, FR-022, FR-024a, FR-025, FR-038).
 *
 * These cover the *convenience* layer. The control is server-side and is proved by
 * `tests/integration/test_contact_submission.py`, which bypasses this file
 * entirely — a browser-driven test of validation proves only that the browser
 * validates.
 */

import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ContactForm } from "../components/ContactForm";

const VALID = {
  name: "Amina Farouk",
  email: "amina@example.com",
  subject: "Approvals",
  message: "We have twelve approval steps and no record of who signed what.",
};

async function fillValid(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText(/your name/i), VALID.name);
  await user.type(screen.getByLabelText(/email address/i), VALID.email);
  await user.type(screen.getByLabelText(/subject/i), VALID.subject);
  await user.type(screen.getByLabelText(/^message/i), VALID.message);
}

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({ ok: true, status: 202, json: async () => ({}) }) as Response),
  );
});

afterEach(() => vi.restoreAllMocks());

describe("validation", () => {
  it("refuses an empty submission and names each field", async () => {
    const user = userEvent.setup();
    render(<ContactForm />);
    await user.click(screen.getByRole("button", { name: /send message/i }));

    expect(await screen.findByText(/please tell us your name/i)).toBeInTheDocument();
    expect(screen.getByText(/please give us an email address/i)).toBeInTheDocument();
    expect(screen.getByText(/please add a subject/i)).toBeInTheDocument();
    expect(screen.getByText(/please write your message/i)).toBeInTheDocument();
  });

  it("does not send anything when input is invalid", async () => {
    const user = userEvent.setup();
    render(<ContactForm />);
    await user.click(screen.getByRole("button", { name: /send message/i }));
    expect(fetch).not.toHaveBeenCalled();
  });

  it("names the email field for a malformed address", async () => {
    const user = userEvent.setup();
    render(<ContactForm />);
    await fillValid(user);
    await user.clear(screen.getByLabelText(/email address/i));
    await user.type(screen.getByLabelText(/email address/i), "not-an-email");
    await user.click(screen.getByRole("button", { name: /send message/i }));

    expect(await screen.findByText(/does not look like an email address/i)).toBeInTheDocument();
  });

  it("keeps everything the visitor already typed", async () => {
    // FR-021 — a refused submission must not cost them their message.
    const user = userEvent.setup();
    render(<ContactForm />);
    await user.type(screen.getByLabelText(/^message/i), VALID.message);
    await user.click(screen.getByRole("button", { name: /send message/i }));

    await screen.findByText(/please tell us your name/i);
    expect(screen.getByLabelText(/^message/i)).toHaveValue(VALID.message);
  });

  it("marks the failing control as invalid", async () => {
    const user = userEvent.setup();
    render(<ContactForm />);
    await user.click(screen.getByRole("button", { name: /send message/i }));

    await screen.findByText(/please tell us your name/i);
    expect(screen.getByLabelText(/your name/i)).toHaveAttribute("aria-invalid", "true");
  });

  it("associates each message with its field for assistive technology", async () => {
    const user = userEvent.setup();
    render(<ContactForm />);
    await user.click(screen.getByRole("button", { name: /send message/i }));

    const control = await screen.findByLabelText(/your name/i);
    const describedBy = control.getAttribute("aria-describedby");
    expect(describedBy).toBeTruthy();
    expect(document.getElementById(describedBy!)?.textContent).toMatch(/your name/i);
  });
});

describe("success state", () => {
  it("confirms explicitly rather than silently clearing", async () => {
    const user = userEvent.setup();
    render(<ContactForm />);
    await fillValid(user);
    await user.click(screen.getByRole("button", { name: /send message/i }));

    expect(await screen.findByText(/your message has been received/i)).toBeInTheDocument();
  });

  it("removes the form so the same message cannot be sent twice by accident", async () => {
    // FR-022 — the client half of duplicate prevention. The server half is the
    // content-hash window, tested in the integration suite.
    const user = userEvent.setup();
    render(<ContactForm />);
    await fillValid(user);
    await user.click(screen.getByRole("button", { name: /send message/i }));

    await screen.findByText(/your message has been received/i);
    expect(screen.queryByRole("button", { name: /send message/i })).not.toBeInTheDocument();
  });
});

describe("failure state", () => {
  it("never reports success when the request failed", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("network down");
      }),
    );
    const user = userEvent.setup();
    render(<ContactForm />);
    await fillValid(user);
    await user.click(screen.getByRole("button", { name: /send message/i }));

    expect(await screen.findByText(/was not sent/i)).toBeInTheDocument();
    expect(screen.queryByText(/has been received/i)).not.toBeInTheDocument();
  });

  it("surfaces server-side field errors the client rules did not catch", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          ({
            ok: false,
            status: 422,
            json: async () => ({
              errors: [{ field: "sender_email", message: "That domain is not accepted." }],
            }),
          }) as Response,
      ),
    );
    const user = userEvent.setup();
    render(<ContactForm />);
    await fillValid(user);
    await user.click(screen.getByRole("button", { name: /send message/i }));

    expect(await screen.findByText(/that domain is not accepted/i)).toBeInTheDocument();
  });
});

describe("collection notice", () => {
  it("states what is collected and for how long, at the point of collection", async () => {
    // FR-024a / FR-024b — not buried in a policy page nobody opens.
    render(<ContactForm />);
    await waitFor(() =>
      expect(screen.getByText(/delete them after 90 days/i)).toBeInTheDocument(),
    );
  });
});

describe("the loading state waits 150ms (FR-027a)", () => {
  /**
   * The requirement names two thresholds so SC-014's prohibition on an indefinite
   * loading state has bounds. The 10-second bound lives in `lib/api.ts` and is
   * measured by `e2e/performance.spec.ts`; this half did not exist at all — the
   * button switched to "Sending…" on the first frame, so a 30ms response produced a
   * visible flicker that reads as a glitch rather than as progress.
   */
  /** `fireEvent` rather than `userEvent`: these cases drive fake timers, and
   *  user-event's own scheduling fights them. The field regexes match the helper at
   *  the top of this file — the visible labels carry a required marker. */
  function fillAndSubmit() {
    fireEvent.change(screen.getByLabelText(/your name/i), { target: { value: VALID.name } });
    fireEvent.change(screen.getByLabelText(/email address/i), { target: { value: VALID.email } });
    fireEvent.change(screen.getByLabelText(/subject/i), { target: { value: VALID.subject } });
    fireEvent.change(screen.getByLabelText(/^message/i), { target: { value: VALID.message } });
    fireEvent.submit(screen.getByRole("form", { name: "Contact form" }));
  }

  it("shows no loading state before the threshold", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: false });
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise(() => {})),
    );
    render(<ContactForm />);
    fillAndSubmit();

    await act(async () => {
      vi.advanceTimersByTime(140);
    });
    expect(screen.getByRole("button", { name: /send message/i })).toBeInTheDocument();
    expect(screen.queryByText("Sending…")).not.toBeInTheDocument();

    vi.useRealTimers();
  });

  it("shows it once the threshold passes", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: false });
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise(() => {})),
    );
    render(<ContactForm />);
    fillAndSubmit();

    await act(async () => {
      vi.advanceTimersByTime(200);
    });
    expect(screen.getByText("Sending…")).toBeInTheDocument();

    vi.useRealTimers();
  });

  it("disables the control immediately, threshold or not", async () => {
    // The disabled state is a duplicate-submission guard (FR-022), not a loading
    // indicator. Delaying it too would open a 150ms window for a double click —
    // exactly the accidental duplicate FR-022 exists to prevent.
    vi.useFakeTimers({ shouldAdvanceTime: false });
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise(() => {})),
    );
    render(<ContactForm />);
    fillAndSubmit();

    await act(async () => {
      vi.advanceTimersByTime(10);
    });
    expect(screen.getByRole("button", { name: /send/i })).toBeDisabled();

    vi.useRealTimers();
  });
});

describe("the per-address bound (FR-024d)", () => {
  /**
   * A 429 had never reached this component. `submitContact` threw `ApiError` for
   * any status but 202 and 422, the catch-all set `status="failed"`, and the form
   * rendered "We could not reach our systems just now. Nothing was saved — please
   * try again in a moment." Every clause of that is false for a bounded submission:
   * the systems were reached, the message was understood and refused on purpose,
   * and "in a moment" is wrong by an hour.
   *
   * Being wrong is worse than being generic here, because it invites exactly the
   * retry the bound exists to stop.
   */
  const SERVER_MESSAGE =
    "We have received several messages from you recently. Please try again later, or write to us directly.";

  function bounded() {
    return vi.fn(async () => ({
      ok: false,
      status: 429,
      json: async () => ({ title: "Too many messages", status: 429, detail: SERVER_MESSAGE }),
    }));
  }

  it("shows the server's message rather than an outage message", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", bounded());
    render(<ContactForm />);
    await fillValid(user);
    await user.click(screen.getByRole("button", { name: /send message/i }));

    expect(await screen.findByText(SERVER_MESSAGE)).toBeInTheDocument();
    expect(screen.queryByText(/could not reach our systems/i)).not.toBeInTheDocument();
  });

  it("does not report the submission as sent", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", bounded());
    render(<ContactForm />);
    await fillValid(user);
    await user.click(screen.getByRole("button", { name: /send message/i }));

    await screen.findByText(SERVER_MESSAGE);
    expect(screen.queryByText(/thank you/i)).not.toBeInTheDocument();
  });

  it("keeps what the visitor typed", async () => {
    // FR-021 requires this on validation failure, and the same reasoning applies:
    // the message is still worth sending, just not now.
    const user = userEvent.setup();
    vi.stubGlobal("fetch", bounded());
    render(<ContactForm />);
    await fillValid(user);
    await user.click(screen.getByRole("button", { name: /send message/i }));

    await screen.findByText(SERVER_MESSAGE);
    expect(screen.getByLabelText(/^message/i)).toHaveValue(VALID.message);
    expect(screen.getByLabelText(/your name/i)).toHaveValue(VALID.name);
  });

  it("announces the refusal to assistive technology", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", bounded());
    render(<ContactForm />);
    await fillValid(user);
    await user.click(screen.getByRole("button", { name: /send message/i }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain(SERVER_MESSAGE);
  });

  it("leaves the control usable", async () => {
    // T113's rule: reporting a problem and staying disabled is a second dead end.
    const user = userEvent.setup();
    vi.stubGlobal("fetch", bounded());
    render(<ContactForm />);
    await fillValid(user);
    await user.click(screen.getByRole("button", { name: /send message/i }));

    await screen.findByText(SERVER_MESSAGE);
    expect(screen.getByRole("button", { name: /send message/i })).toBeEnabled();
  });

  it("still shows the outage message when the server is genuinely unreachable", async () => {
    // The distinction only means something if the other branch survives.
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("Failed to fetch");
      }),
    );
    render(<ContactForm />);
    await fillValid(user);
    await user.click(screen.getByRole("button", { name: /send message/i }));

    expect(await screen.findByText(/could not reach our systems/i)).toBeInTheDocument();
  });
});
