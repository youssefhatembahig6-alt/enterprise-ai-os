import { Button } from "@eaios/ui";

/**
 * Careers filters (FR-014).
 *
 * A plain GET form, not a client component. Three consequences, all wanted:
 * the applied filter lives in the query string so the view is shareable
 * (contracts/routes.md), the page stays server-rendered, and the filter works
 * with no JavaScript at all.
 */
export function VacancyFilters({
  offices,
  departments,
  selected,
}: {
  offices: string[];
  departments: string[];
  selected: { office?: string | undefined; department?: string | undefined };
}) {
  const active = selected.office || selected.department;

  return (
    <form method="get" action="/careers" className="eaios-section" aria-label="Filter roles">
      <div style={{ display: "flex", flexWrap: "wrap", gap: "1rem", alignItems: "flex-end" }}>
        <div className="eaios-field" style={{ marginBlockEnd: 0, minWidth: "12rem" }}>
          <label className="eaios-field__label" htmlFor="office">
            Office
          </label>
          <select
            id="office"
            name="office"
            className="eaios-field__control"
            defaultValue={selected.office ?? ""}
          >
            <option value="">All offices</option>
            {offices.map((office) => (
              <option key={office} value={office}>
                {office}
              </option>
            ))}
          </select>
        </div>

        <div className="eaios-field" style={{ marginBlockEnd: 0, minWidth: "12rem" }}>
          <label className="eaios-field__label" htmlFor="department">
            Team
          </label>
          <select
            id="department"
            name="department"
            className="eaios-field__control"
            defaultValue={selected.department ?? ""}
          >
            <option value="">All teams</option>
            {departments.map((department) => (
              <option key={department} value={department}>
                {department}
              </option>
            ))}
          </select>
        </div>

        <Button type="submit">Apply filters</Button>

        {/* FR-026 — the applied filter must be visible *and* removable. */}
        {active ? (
          <a href="/careers" className="eaios-button eaios-button--secondary">
            Clear filters
          </a>
        ) : null}
      </div>
    </form>
  );
}
