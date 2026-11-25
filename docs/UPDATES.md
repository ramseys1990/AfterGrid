# Application updates

AfterGrid uses the reviewed image references in each module's Compose file. The local version report (administrator-only) displays that configured reference, the image IDs used by existing containers and the image ID currently associated with the configured reference in local Docker storage, if available. An image ID is not an application semantic version. Matching local IDs is not proof that a registry has no newer build. No registry requests are made by viewing versions.

Manual Update requires explicit acknowledgment of a current application-consistent backup and is only accepted for a running supported module. This is an administrator attestation, not a verified snapshot. Compose pulls the configured image and recreates the project if needed, then checks readiness. It does not select an arbitrary new tag, prune old images, remove data or attempt automatic rollback of schema migrations. Recent update jobs and their outcomes appear in the version details; existing installation activity provides job output. Update can briefly interrupt service. If an update fails, inspect the logs; recovery may require both the prior image and a consistent backup. Do not use reinstall as an upgrade procedure.

Routing updates are explicitly blocked until graph migration and recovery are validated. A new reviewed tag is normally introduced through a future AfterGrid release. Core upgrades, verified pre-update backup, automatic per-module scheduling and exact image recovery remain separate work. No automatic update is enabled.

## Explicit online registry check

The administrator can separately request a registry check for the exact reviewed Compose image reference. Docker Buildx inspects raw registry manifests without pulling image layers or changing containers. For an image index, select a unique manifest matching the Docker daemon OS and architecture; ambiguous variants return unavailable. Compare the image config digest (not the manifest/index digest) to installed Docker image IDs. A single-manifest result does not independently establish its platform. The report is read-only, time-bounded and uncached; registry or platform failures are unknown, never up to date. Only one registry check runs at a time. Current modules are single-service projects.

A digest-pinned reference remains fixed. A tag can be republished, so a different config digest does not mean a newer or compatible version. This check does not enumerate upstream tags, bypass the reviewed version policy, automatically install anything or verify signatures. A release with reviewed Compose image changes is still the path to a different version tag. The check requires internet access and is never run automatically. Native registry availability is independent of local operation.

## Next milestone: backup-aware automatic updates (implementation plan)

Keep Compose as the lifecycle engine and Kopia as the backup engine. Do not
introduce a second container orchestrator, general-purpose updater, automatic
tag crawler, mutable latest channel or arbitrary image overrides. No automatic
update is enabled by this plan.

### Candidate and opt-in rules

- Review a new release reference and platform-specific expected image identity
  in the repository before it is eligible for automatic installation. A
  registry mismatch or republished tag alone is not an approved upgrade.
- Initially support one digest-pinned, single-service reader: Kiwix. Its
  content mount is read-only and it has an existing native content backup
  and verification path. Core content admission must still exclude concurrent
  library writes. Retain the old image and reviewed Compose configuration.
- Application updates are off by default and individually opt-in. Require
  an administrator-defined maintenance window before unattended execution.
  Do not attempt updates in either recovery mode, during recovery maintenance,
  active worker jobs, content changes or an unresolved update failure.
- A reviewed release needs an explicit new target; a deployment with no
  approved candidate should report "no approved update", not pull latest.
  Keep manual update behavior separate from the unattended path.

### First executable slice and gates

1. Add a read-only candidate/eligibility report using the current reviewed
   module definition, local Docker identity and explicit registry check.
   Distinguish missing candidate, matching image, unknown registry and blocked
   admission. No writes or container actions.
2. Implement a single administrator-confirmed guarded Kiwix update using
   existing worker jobs. Capture and fully verify an exact new native content
   snapshot protected at creation. Record its manifest and job IDs plus
   original image identity. Preserve the old image and content; defer if a
   fresh verified pin cannot be confirmed.
3. Use only the reviewed exact target, check registry identity and pulled
   image identity, let Compose recreate the reviewed service, check actual
   readiness and fixture content readability. Record original and resulting
   IDs. Never prune or delete persistent data. Recheck all admission
   conditions before execution; do not assume a previous backup proves
   consistency after intervening content writes.
4. Test failed pull, unexpected digest, failed readiness, missed window,
   interrupted job, disconnected registry and pre-update backup failure.
   Pause on ambiguous outcomes; no unattended retry. For the reader-only
   pilot, test restoration of the exact previous image without replacing
   content. Do not imply application schema rollback for database-backed apps.
5. Only after the guarded pilot passes, connect opt-in per-module scheduling
   to the existing portal admission loop. Retain manual updates and make
   status and failure visible. No catch-up burst after an offline period.

### Scope held back

Kopia itself, worker/core upgrades, MicroTAK, routing graph migrations and
database-backed native applications are not unattended pilot targets. Review
each application's version compatibility, data/credential backup coverage,
migration behavior and actual rollback or recovery procedure before expanding.
A pinned backup is not a complete system recovery package, and pin storage
needs explicit operator review; do not automatically unpin old recovery points.
Native and physical clean-host acceptance remain distinct.

### Advisory eligibility implementation

The first read-only slice is implemented. The repository-owned
`modules/kiwix/update-candidate.json` deliberately has a null candidate.
A later reviewed release must provide the exact digest-pinned Kiwix Compose
target and approved source/target image config IDs for each supported
platform (linux/amd64 or linux/arm64). The worker requires exact Compose
target agreement, a known approved installed starting point, a ready
reader, connected Kopia and idle worker; an explicit online check also
requires matching registry config and platform-manifest evidence. A
single manifest without confirmed platform selection is not sufficient.
Unknown registry, recovery modes, missing candidates and mismatched
identities do not authorize an update. Local inspection does not contact
the registry. The portal serializes the explicit online check with its
existing maintenance/content admission. Results are advisory; no image
pull, backup, update execution or automatic scheduling is exposed here.

### Protected preparation rehearsal

An explicit administrator-confirmed preparation is accepted only for a
repository-approved Kiwix transition. The worker rechecks online registry
and installed image identity, verifies the old image exists by ID, holds
the existing content guard throughout new pin-at-creation snapshot and full
exact-manifest read verification, rechecks the native pin and local identity,
and records evidence only after successful guard release. No image pulls,
tags, service recreation, pruning or data replacement occur. Preparation
evidence is historical, **never reusable authorization**: the eventual
guarded update must repeat capture and verification under its own continuous
guard. External content writers remain the operator's responsibility.
The approved candidate remains null; the native fixture confirms rejection
in that state, while focused regression tests cover the mocked successful
and failed preparation sequences. Actual positive native transition acceptance
and preservation of the prior image against pruning are still outstanding.
