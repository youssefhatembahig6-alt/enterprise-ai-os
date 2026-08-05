import type { Metadata } from "next";

import { Card, EmptyState, ErrorState, Text } from "@eaios/ui";

import { ContactForm } from "../../components/ContactForm";
import { RetryButton } from "../../components/RetryButton";
import { getCompany, getOffices } from "../../lib/api";
import { pageMetadata } from "../../lib/metadata";

export const metadata: Metadata = pageMetadata({
  title: "Contact",
  description: "Get in touch with NileTech Solutions in Cairo, Alexandria, or Dubai.",
  path: "/contact",
});

/** FR-018 — every office with city, country, and address, plus a general enquiry
 *  address, alongside the form. */
export default async function ContactPage() {
  let offices: Awaited<ReturnType<typeof getOffices>> = [];
  let domain: string | null = null;
  let failed = false;

  try {
    const [officeList, company] = await Promise.all([getOffices(), getCompany()]);
    offices = officeList;
    domain = company.domain;
  } catch {
    failed = true;
  }

  return (
    <>
      <h1>Contact us</h1>
      <p className="eaios-hero__lede">
        Tell us what you are trying to solve. Someone who has built something similar
        will reply.
      </p>

      <div
        style={{
          display: "grid",
          gap: "var(--space-7)",
          gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 320px), 1fr))",
        }}
      >
        <section aria-labelledby="send-message">
          <h2 id="send-message">Send us a message</h2>
          {/* The form is a separate region from the office details, so a failure
              loading offices does not take the form down with it (FR-030). */}
          <ContactForm />
        </section>

        <section aria-labelledby="where-to-find-us">
          <h2 id="where-to-find-us">Where to find us</h2>

          {failed ? (
            <ErrorState
              title="Office details could not be loaded"
              retry={<RetryButton label="Reload our addresses" />}
            >
              <p>You can still send a message using the form.</p>
            </ErrorState>
          ) : (
            <>
              {domain ? (
                <p>
                  General enquiries: <a href={`mailto:hello@${domain}`}>hello@{domain}</a>
                </p>
              ) : null}

              {/* FR-026 — the offices region has an empty case of its own, and it
                  went unimplemented: an office list that came back empty left this
                  region as a heading above nothing, which reads as breakage rather
                  than as an answer. This page does not use `Section`, so it did not
                  inherit that component's empty state. */}
              {offices.length === 0 ? (
                <EmptyState
                  title="Office details are not available right now"
                  action={
                    <a href="/about" className="eaios-button eaios-button--secondary">
                      Read about us
                    </a>
                  }
                >
                  <p>
                    We could not list our offices at the moment. The form beside this
                    reaches us either way.
                  </p>
                </EmptyState>
              ) : null}

              <div style={{ display: "grid", gap: "var(--space-4)" }}>
                {offices.map((office) => (
                  <Card
                    key={`${office.city}-${office.country}`}
                    title={
                      office.is_headquarters
                        ? `${office.city} (Headquarters)`
                        : office.city
                    }
                  >
                    <p><Text value={office.address} /></p>
                    <p><Text value={office.country} /></p>
                  </Card>
                ))}
              </div>
            </>
          )}
        </section>
      </div>
    </>
  );
}
