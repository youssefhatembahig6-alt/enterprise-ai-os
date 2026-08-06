/**
 * Shared UI primitives.
 *
 * Feature 001 created this package and left it empty on purpose — decision D1
 * deferred every UI surface, so there was nothing to share. Feature 002 fills it
 * rather than building components inside `apps/web`, because the employee portal is
 * the next surface and will need the same pieces. Building them in the website
 * first and extracting later is how two divergent design systems get created.
 *
 * Styling comes from `tokens.css` and `components.css`, imported once by the
 * consuming app's root layout.
 */

export { Alert } from "./primitives/Alert";
export { Button } from "./primitives/Button";
export { Card } from "./primitives/Card";
export { Field } from "./primitives/Field";
export { Skeleton } from "./primitives/Skeleton";
export { Tag } from "./primitives/Tag";
export { Text } from "./primitives/Text";

export { AccessDeniedState } from "./patterns/AccessDeniedState";
export { EmptyState } from "./patterns/EmptyState";
export { ErrorState } from "./patterns/ErrorState";
export { PageHeader } from "./patterns/PageHeader";
export { SectionGrid } from "./patterns/SectionGrid";
export { SessionExpiredState } from "./patterns/SessionExpiredState";

export const UI_PACKAGE_VERSION = "0.4.0";
