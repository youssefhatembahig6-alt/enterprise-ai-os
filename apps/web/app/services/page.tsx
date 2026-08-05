import type { Metadata } from "next";

import { Card, Text } from "@eaios/ui";

import { Section } from "../../components/Section";
import { getServices } from "../../lib/api";
import { pageMetadata } from "../../lib/metadata";

export const metadata: Metadata = pageMetadata({
  title: "Services",
  description:
    "Automation, integration, and managed delivery services from NileTech Solutions.",
  path: "/services",
});

/** FR-011 — every generated service, in the generator's display order. */
export default function ServicesPage() {
  return (
    <>
      <h1>Services</h1>
      <p className="eaios-hero__lede">
        How we help enterprises replace manual process with governed, auditable automation.
      </p>

      <Section
        title="What we do"
        id="services-list"
        load={getServices}
        empty={{
          title: "No services are listed yet",
          body: "Our service catalogue is being updated. Please get in touch and we will talk you through what we offer.",
        }}
      >
        {(services) =>
          services.map((service) => (
            <Card key={service.name} title={service.name}>
              <p>
                <strong><Text value={service.summary} /></strong>
              </p>
              <p><Text value={service.description} /></p>
            </Card>
          ))
        }
      </Section>
    </>
  );
}
