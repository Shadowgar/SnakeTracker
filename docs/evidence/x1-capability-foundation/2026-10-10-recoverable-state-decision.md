# X1 recovered-state policy and continuation boundaries

Owner decision: October 10, 2026. Engineering policy authorized; X1 remains unaccepted.

The owner approves compatibility validation over the complete SQLite-recoverable
committed state acquired from a consistent, protected view before mutable startup.
This excludes a claim that arbitrary clean historical loss is detectable when all
independent evidence of later commits is absent. SQLite integrity checking alone
does not establish historical completeness.

The approval retains physical preservation of the original database, WAL and SHM;
visibility of recoverable committed WAL; complete retained-history contract and
required-identity validation; conservative rejection of detectable or ambiguous
damage; and uninterrupted writer exclusion through admission to normal startup.
An independent durable history authority is not authorized.

The prepared application-only preflight does not establish those storage guarantees.
Its logical SQLite read-only connection can create or modify original SHM. The
existing private-filesystem experiment excludes independent writers while read-only,
but releasing it globally admits an unrelated writer. Current data resides on the
shared SD/ext4 root; no supported local SSD snapshot workspace is available.

Protected acquisition and handoff implementation is stopped at the expressly required
operational authorization boundary. Before continuing that portion, the owner must
approve a dedicated storage/access boundary and trusted supervisor that controls all
writable aliases and existing writers, grants access only to the approved runtime
without a release window, and fails closed on unresolved access. A supported SSD
workspace additionally needs approved ownership, bounded capacity/reservation and
supervised inactive-artifact cleanup. No such operational change is implemented here.

The owner separately authorizes the narrow registration-writer metadata and private
operator-diagnostic corrections. They do not qualify the unresolved storage mechanism.
Historical replay and completed retries remain independent of current write policy.

The prior twenty-file patch and all prior qualification evidence remain preserved.
No production operations, protected-document amendments, merge or X2 work are authorized.
ADR-0045, ADR-0046 and ADR-0047 remain Proposed. Implementation, engineering qualification,
operational release readiness and owner acceptance remain separate decisions.
