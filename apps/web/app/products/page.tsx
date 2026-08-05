import type { Metadata } from "next";

import { Card, Text } from "@eaios/ui";

import { Section } from "../../components/Section";
import { getProducts } from "../../lib/api";
import { pageMetadata } from "../../lib/metadata";

export const metadata: Metadata = pageMetadata({
  title: "Products",
  description: "Product offerings from NileTech Solutions.",
  path: "/products",
});

/**
 * FR-012 — the *public* product offerings only.
 *
 * The internal sellable catalogue, its prices, and its tiers are a different table
 * that no public route reads; `tests/integration/test_public_content.py` asserts it
 * is unreachable rather than merely unrendered.
 */
export default function ProductsPage() {
  return (
    <>
      <h1>Products</h1>
      <p className="eaios-hero__lede">
        Platforms we build on, and run, for customers across Egypt and the UAE.
      </p>

      <Section
        title="Our products"
        id="products-list"
        load={getProducts}
        empty={{
          title: "No products are listed yet",
          body: "We are preparing our product pages. In the meantime, our services page describes how we work.",
        }}
      >
        {(products) =>
          products.map((product) => (
            <Card key={product.name} title={product.name}>
              <p>
                <strong><Text value={product.tagline} /></strong>
              </p>
              <p><Text value={product.description} /></p>
            </Card>
          ))
        }
      </Section>
    </>
  );
}
