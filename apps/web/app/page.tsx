import type { Metadata } from "next";
import Link from "next/link";

import { Card, Tag, Text } from "@eaios/ui";

import { Section } from "../components/Section";
import { getNews, getProducts, getServices, getVacancies } from "../lib/api";
import { pageMetadata } from "../lib/metadata";

/**
 * Declared explicitly rather than inherited from the root layout.
 *
 * The layout supplies a title and description, but **not** a canonical address or
 * social-preview tags — so the home page, the most-shared page on any site, had
 * neither until the metadata sweep in `e2e/metadata.spec.ts` said so. FR-040 and
 * FR-042 require both on every page.
 */
export const metadata: Metadata = pageMetadata({
  title: "NileTech Solutions — Software and business automation",
  description:
    "NileTech Solutions builds and runs business automation for enterprises in Cairo, Alexandria, and Dubai.",
  path: "/",
});

/**
 * Home (spec 002 FR-005) — hero, then summaries of services, **products**, news,
 * and openings, each linking to its full page.
 *
 * Products were absent from this page from the day it was written. FR-005 names
 * four things the home page must summarize and three were here; every "Products"
 * string in the served HTML was a navigation link, so a visitor arriving at the
 * root — the P1 journey — was never shown that the company has products at all.
 * Four convergence runs went past it, because each one checked how this page
 * *behaves* (its states, its metadata, its timing) and none checked its contents
 * against the sentence that specifies them.
 *
 * The `more` links are the requirement's second clause, which was also unmet: each
 * block summarized without offering the way onward.
 *
 * The hero copy is **interface copy**, exempt from FR-006 under FR-006a. That
 * exemption exists because the dataset carries no positioning field: `companies`
 * holds name, domain, status, and currency, so a hero sourced from data was
 * impossible. The copy therefore states nothing the dataset could contradict — no
 * headcount, no client names, no figures. Everything below the hero is generated
 * content.
 */
export default function HomePage() {
  return (
    <>
      <section className="eaios-section" aria-labelledby="hero">
        <h1 id="hero">Business automation that leaves a record</h1>
        <p className="eaios-hero__lede">
          NileTech Solutions builds and runs the systems that move work through an
          organisation — approvals, records, reporting, and the integrations between them.
        </p>
        <div className="eaios-actions">
          <Link href="/services" className="eaios-button">
            Explore our services
          </Link>
          <Link href="/contact" className="eaios-button eaios-button--secondary">
            Talk to us
          </Link>
        </div>
      </section>

      <Section
        title="What we do"
        id="home-services"
        // Three is the summary; the full set lives on /services (FR-005).
        load={async () => (await getServices()).slice(0, 3)}
        empty={{
          title: "Our services are being updated",
          body: "Get in touch and we will talk you through how we work.",
        }}
        more={{ href: "/services", label: "See all services" }}
      >
        {(services) =>
          services.map((service) => (
            <Card key={service.name} title={service.name}>
              <p><Text value={service.summary} /></p>
              <Link href="/services">Read more</Link>
            </Card>
          ))
        }
      </Section>

      <Section
        title="What we build"
        id="home-products"
        load={async () => (await getProducts()).slice(0, 3)}
        empty={{
          title: "Our products are being updated",
          body: "Get in touch and we will show you what we are working on.",
        }}
        more={{ href: "/products", label: "See all products" }}
      >
        {(products) =>
          products.map((product) => (
            <Card key={product.name} title={product.name}>
              <p><Text value={product.tagline} /></p>
              <Link href="/products">Read more</Link>
            </Card>
          ))
        }
      </Section>

      <Section
        title="Latest news"
        id="home-news"
        load={async () => (await getNews(3)).items}
        empty={{
          title: "No announcements yet",
          body: "There is nothing to report just now. Check back soon.",
        }}
        more={{ href: "/news", label: "All announcements" }}
      >
        {(items) =>
          items.map((item) => (
            <Card key={item.slug} title={item.headline}>
              <p>
                <time dateTime={item.published_on}>{item.published_on}</time>
              </p>
              <Link href={`/news/${item.slug}`}>Read the announcement</Link>
            </Card>
          ))
        }
      </Section>

      <Section
        title="Open roles"
        id="home-careers"
        load={async () => (await getVacancies()).slice(0, 3)}
        empty={{
          title: "No open roles right now",
          body: "We are not hiring at the moment, but we are always glad to hear from good people.",
        }}
        more={{ href: "/careers", label: "All open roles" }}
      >
        {(vacancies) =>
          vacancies.map((vacancy) => (
            <Card key={vacancy.slug} title={vacancy.title}>
              <p>
                <Tag>{vacancy.department}</Tag>{" "}
                <Tag>
                  {vacancy.office_city}, {vacancy.office_country}
                </Tag>
              </p>
              <Link href={`/careers/${vacancy.slug}`}>See the role</Link>
            </Card>
          ))
        }
      </Section>
    </>
  );
}
