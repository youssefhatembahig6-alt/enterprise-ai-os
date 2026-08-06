"""What counts as sensitive, in one place (spec 003 FR-017a, FR-017b).

FR-017b requires exactly this: one definition, consulted by the decision, never
restated at a call site. Adding a resource type is a change here and nowhere else.

The rule it implements has two halves. Every **denial** is audited — no exemption, no
coalescing, they are the security signal. **Allows** are audited only for the four
cases enumerated below.

The second half is a deliberate narrowing, and it is worth being explicit about why,
because an absent audit entry is indistinguishable from a broken audit writer.
Auditing every read makes one page view write dozens of rows and buries the entries an
auditor actually needs — feature 002 found that from the other direction, having to
bound refusal auditing only after the requirement had produced its own
denial-of-service surface. Principle X asks "who saw this?", which is a question about
sensitive material, not about someone loading their own name.
"""

from __future__ import annotations

from ..classification import Classification
from .context import AccessContext
from .decision import ResourceDescriptor, ResourceKind

__all__ = ["ORDINARY_CLASSIFICATION", "is_sensitive"]

#: The highest level that is *not* by itself sensitive. Anything above it is.
ORDINARY_CLASSIFICATION = Classification.INTERNAL


def is_sensitive(resource: ResourceDescriptor, subject: AccessContext) -> bool:
    """True when an **allow** for this resource must be audited.

    The four clauses are FR-017a's, in its order.
    """
    # 2 — compensation detail of any kind, *including the requester's own*. Listed
    # before clause 1 only because it is the clause that does not follow from
    # ownership: the natural implementation ("sensitive when it belongs to someone
    # else") gets this one wrong, and payroll access is worth recording even when the
    # payroll is yours.
    if resource.kind is ResourceKind.HR_COMPENSATION:
        return True

    # 4 — any read of the audit log itself. Who inspected the record of who saw what
    # is exactly the question the record exists to answer.
    if resource.kind is ResourceKind.AUDIT_LOG:
        return True

    # 3 — anything classified above the ordinary level.
    if resource.classification is not None and resource.classification > ORDINARY_CLASSIFICATION:
        return True

    # 1 — an HR record belonging to someone other than the requester.
    #
    # `DIRECT_REPORTS` is deliberately excluded: the roster carries names, titles, and
    # departments — no HR record content — and every profile it links to is separately
    # decided and separately audited. Auditing the list as well would write an entry
    # every time a manager opened their team page and record nothing the per-profile
    # entries do not already say.
    return resource.kind is ResourceKind.HR_PROFILE and resource.owner_id != subject.user_id
