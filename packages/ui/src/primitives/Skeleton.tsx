/**
 * Placeholder for a client-fetched region that has not resolved (FR-025).
 *
 * `aria-hidden` with a sibling live region is deliberate: announcing a shimmering
 * box tells a screen-reader user nothing. The region's status text is what gets
 * announced (FR-038).
 */
export function Skeleton({ lines = 3 }: { lines?: number }) {
  return (
    <div aria-hidden="true">
      {Array.from({ length: lines }, (_, index) => (
        <div
          key={index}
          className="eaios-skeleton"
          style={{
            height: index === 0 ? "1.6rem" : "1rem",
            width: index === lines - 1 ? "60%" : "100%",
            marginBottom: "0.75rem",
          }}
        />
      ))}
    </div>
  );
}
