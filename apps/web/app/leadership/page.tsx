import type { Metadata } from "next";

import { Card, Text } from "@eaios/ui";

import { Section } from "../../components/Section";
import { getLeadership } from "../../lib/api";
import { pageMetadata } from "../../lib/metadata";

export const metadata: Metadata = pageMetadata({
  title: "Leadership",
  description: "The people leading NileTech Solutions.",
  path: "/leadership",
});

/**
 * FR-013 — name, public title, and biography. Nothing else about the person.
 *
 * Feature 001 generates no photographs, so each profile shows the person's
 * initials in a designed placeholder rather than a broken image or an empty gap
 * (US5/AC3). The placeholder is decorative and hidden from assistive technology:
 * the name beside it is the information.
 */
export default function LeadershipPage() {
  return (
    <>
      <h1>Leadership</h1>
      <p className="eaios-hero__lede">
        The people accountable for what we build and how we run it.
      </p>

      <Section
        title="Our leadership team"
        id="leadership-list"
        load={getLeadership}
        empty={{
          title: "Leadership profiles are unavailable",
          body: "We could not load our leadership team just now. Please try again shortly.",
        }}
      >
        {(leaders) =>
          leaders.map((leader) => (
            <Card key={leader.full_name} title={leader.full_name}>
              <div style={{ display: "flex", gap: "1rem", alignItems: "flex-start" }}>
                <span
                  aria-hidden="true"
                  style={{
                    flex: "0 0 auto",
                    width: "3rem",
                    height: "3rem",
                    borderRadius: "50%",
                    background: "var(--brand-wash)",
                    color: "var(--brand-strong)",
                    display: "inline-flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontWeight: 600,
                  }}
                >
                  {leader.full_name
                    .split(" ")
                    .map((part) => part[0])
                    .slice(0, 2)
                    .join("")}
                </span>
                <div>
                  <p>
                    <strong><Text value={leader.public_title} /></strong>
                  </p>
                  <p><Text value={leader.bio} /></p>
                </div>
              </div>
            </Card>
          ))
        }
      </Section>
    </>
  );
}
