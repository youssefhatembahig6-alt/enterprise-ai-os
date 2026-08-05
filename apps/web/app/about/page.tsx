import type { Metadata } from "next";

import { Card, Text } from "@eaios/ui";

import { Section } from "../../components/Section";
import { getOffices } from "../../lib/api";
import { pageMetadata } from "../../lib/metadata";

export const metadata: Metadata = pageMetadata({
  title: "About",
  description:
    "NileTech Solutions is a software and business-automation company with offices in Cairo, Alexandria, and Dubai.",
  path: "/about",
});

/**
 * FR-010 — every generated office with its city, country, address, and which is
 * the headquarters.
 *
 * The narrative paragraphs are interface copy, exempt from FR-006 under FR-006a,
 * and deliberately state nothing the dataset could contradict — no headcount, no
 * client names, no figures, no office list. The offices below come from the data.
 */
export default function AboutPage() {
  return (
    <>
      <h1>About NileTech Solutions</h1>
      <p className="eaios-hero__lede">
        We build and run the systems that move work through an organisation — approvals,
        records, reporting, and the integrations between them.
      </p>

      <section className="eaios-section" aria-labelledby="about-approach">
        <h2 id="about-approach">How we work</h2>
        <p>
          Most of the organisations we work with do not need new software so much as they
          need the software they already have to talk to each other, and to leave a record
          when it does. We start from the process, not the platform.
        </p>
        <p>
          Every engagement is delivered by a team that stays with the system after it ships.
          We think that is the only honest way to build something an organisation will
          depend on.
        </p>
      </section>

      <Section
        title="Where we are"
        id="about-offices"
        load={getOffices}
        empty={{
          title: "Office information is unavailable",
          body: "We could not load our office list. Please contact us and we will point you to the nearest team.",
        }}
      >
        {(offices) =>
          offices.map((office) => (
            <Card
              key={`${office.city}-${office.country}`}
              title={office.is_headquarters ? `${office.city} (Headquarters)` : office.city}
            >
              <p><Text value={office.address} /></p>
              <p><Text value={office.country} /></p>
            </Card>
          ))
        }
      </Section>
    </>
  );
}
