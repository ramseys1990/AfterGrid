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

### Previous image preservation

Preparation now saves the exact prior Kiwix image ID as a native Docker
archive in the private worker state volume, deduplicated by image ID.
An archive is independently useful even if local Docker images are pruned;
a tag alone is not sufficient. Before publication, verify the archive
checksum and the saved image configuration's SHA-256 against the expected
image ID. Writes are staged and synchronized; invalid existing archives
are not silently overwritten. Space preflight, a 4 GiB archive limit and
a bounded save time apply. An interrupted save can leave private staging
files for operator inspection. No automatic archive removal or load
endpoint is exposed. Preparation evidence records archive bytes and
checksum, not authorization for a later update. The worker-state volume
is local, not an independent off-host backup; these archives are not
included in the current worker recovery export. Preserve important
portable packages separately. The disposable native fixture checks actual
save and load without deleting any image. Positive approved-transition
acceptance remains outstanding.

### Administrator-triggered guarded update

A separate confirmed Kiwix action now repeats the entire preparation under
one content guard, persists pre-update recovery evidence, rechecks registry
and local identity, pulls only the reviewed digest-pinned Compose target,
and refuses recreation unless the pulled image config ID is exactly the
approved target. It records the recreation boundary durably before Compose
up (no pull/build), checks actual reader readiness and installed image ID,
and compares a bounded nonempty native catalog entry-ID sample before and
after. This is a catalog check, not full article retrieval or schema
migration acceptance. Failure/interruption retains prior archive and pin
evidence and blocks another guarded update; no automatic rollback or retry
yet. Existing manual update semantics remain separate. The repository
candidate is still null, so the production action cannot execute until a
reviewed transition is supplied. Positive native transition acceptance,
explicit recovery handling and scheduling are subsequent gates.

### Reader failure recovery

After a guarded Kiwix recreation attempt fails, the worker attempts image-only
rollback while still holding the content guard. It requires unchanged reviewed
Compose file bytes, the exact saved archive and matching checksum/config
identity, and an existing protected snapshot. It restores the local old image
if missing, sets a reserved exact-ID tag and publishes a persistent private
Compose image override with pull policy never. The rollback uses the same
reviewed reader configuration and does not overwrite content. Verify the
installed image and compare the native catalog sample to pre-update evidence.
A restored reader is still a failed update, never a successful upgrade.
Unconfirmed rollback or interruption requires host/operator inspection.
The hold blocks further update, install and restart; Start uses the
exact local recovery tag and refuses pull/build. No automatic hold clearing,
image pruning, data restore or update retry. Host-side lifecycle commands
outside AfterGrid can bypass the hold. The current portable recovery export
does not carry the local hold or image archive; it captures the actual running
container image separately. This is not database migration rollback.
Disposable native reader rollback helper coverage and regressions added;
positive approved-transition acceptance and explicit hold resolution remain
outstanding.

### Update preferences and maintenance windows

The Kiwix pilot accepts a private, persistent, administrator-confirmed
preference and weekly UTC admission window (Monday=0; same-day, 30–360
minutes). Missing preferences are disabled. The report distinguishes an
open window and the next start. An open window is not an execution
authorization or a guarantee that a long verification will finish within
it. No scheduler or registry polling is connected. Saving a preference
does not consent to future execution: separate activation after positive
native acceptance is required. Recovery mode disables mutation. These
local preferences are not included in the current recovery export and
must be configured again after replacement recovery. No other module
has automatic-update eligibility.

### Administrator update health

The local dashboard combines approved candidate, reader state, effective
Compose and installed image identity, rollback hold, maintenance preference
and separate latest guarded, manual and preparation job evidence. A later
preparation cannot conceal an unresolved guarded update. Refresh is
read-only, performs no registry check, full archive read, backup or
container mutation, and labels previous backup and archive evidence as
historical. No unattended dispatch or rollback hold clearing is exposed.

### Rollback resolution preflight

The health dashboard now explains local prerequisites for hold resolution: a matching failed guarded job and recorded restored image/pin/archive, an idle worker, actual readiness and the exact installed rollback image, and the unoverridden digest-pinned base Compose target resolving locally to that same recovered image. Base inspection is config-only; no registry lookup or pull. A mismatched base target must not be reactivated by deleting the override. Local prerequisites are advisory only, not clearance: explicit fresh native archive/pin/catalog checks and a controlled resolution operation remain required. No hold mutation or retry is enabled by this slice.

### Explicit hold resolution

The administrator may queue an exact failed-job/image resolution only when the unoverridden reviewed base Compose target resolves to the recovered image locally. The worker repeats local checks under the content guard, validates the previous image archive, fully reads the pinned native snapshot again, checks the pin again, compares the recovered catalog, and checks the base fingerprint before removing the override. No container recreation, pull or data replacement. The original failed job remains failed; only a matching successful resolution job clears its admission block. An interruption or failure leaves the original outcome unresolved; a crash after override removal may require host inspection. A changed base target is not automatically rewritten. This is not retry authorization or automatic scheduling activation. Regression coverage added; native acceptance pending.

### Gated automatic dispatch

The existing portal scheduler now includes a Kiwix dispatch path with a release gate (`EXECUTION_ENABLED=False`), separate administrator activation, private persistent window claim, local eligibility, one online identity check, idle/maintenance and window recheck, and the same guarded worker queue. A claimed window is never retried after a timeout, rejection or process restart. Changing preferences disables activation. Disabled release or preference performs no registry polling. The activation endpoint cannot enable execution while the release gate is false. This intentionally leaves unattended execution off until native resolution and scheduler acceptance are confirmed. No new service or installation process is introduced.


## Core update preparation (restricted pilot)

The host-only `core_update.py` prepares a reviewed exact commit archive with an independently reviewed SHA-256. It builds two isolated candidate image tags, records the original healthy core/worker container and image identities plus configuration hashes, and leaves all running services unchanged. Example: `sudo python3 /opt/aftergrid/core_update.py /path/to/reviewed.tar.gz --commit <40-hex-commit> --sha256 <64-hex-sha256>`. The operator supplies the reviewed archive; a checksum is integrity evidence, not a signature. Only unchanged base Compose and module trees are accepted in this first slice. No automatic activation, database migration, rollback readiness, image pruning, or browser root command is claimed. Next: verified consistent core and worker snapshots, maintenance admission, exact image retention, controlled replacement and rollback acceptance.


### Pre-activation recovery evidence

After preparing a candidate, begin existing recovery maintenance with no optional modules selected. Create protected core and worker snapshots, run their isolated restore verifications, generate the final recovery inventory and seal maintenance. Run `sudo python3 /opt/aftergrid/core_update.py --check-backups /opt/aftergrid-updates/<candidate>` to check the original running core/worker identity, unchanged configuration, sealed inventory hash, recent post-preparation captures, exact successful verification jobs, worker envelope digest and current native Kopia pins. This is read-only advisory evidence, not an activation authorization. A later seal release or state change invalidates it; activation must repeat admission and separately retain exact prior images and consistent rollback data. During capture maintenance the protected snapshot endpoint now admits only core and worker sources for the maintenance owner. No new backup engine or automatic deletion.


### Exact prior-image retention

Run `sudo python3 /opt/aftergrid/core_update.py --retain-previous /opt/aftergrid-updates/<candidate>` before taking the final fresh sealed backups. It records dedicated prior image tags, saves the two exact image IDs using the existing Docker archive helper, checks the Docker archive configuration digests and hashes the full archive. It produces candidate and previous image-only Compose override files with pull policy never, plus a private retention record. It does not run Compose or replace containers. Archive configuration verification is not a native image-load test, nor a consistent state rollback; retain the files and do not prune. Activation and rollback remain unavailable until the durable maintenance boundary and state recovery are accepted.


### Durable update maintenance claim

A restricted administrator API can claim a matching sealed core-only inventory using the candidate plan SHA-256. The persistent `updating` phase blocks ordinary portal mutations, login/logout, scheduled work and ordinary maintenance release across core restarts. No browser control exposes the claim yet. The host-only `--check-activation CANDIDATE` checks the matching hold, retained archive hash and image IDs, both exact no-pull overrides, current configuration and fresh native pinned backup evidence. It deliberately reports activation disabled and consistent local checkpoint absent. `--cancel-claim CANDIDATE` returns an unactivated claim to sealed maintenance only if the original healthy containers still match and no activation journal exists. Then release maintenance normally. The claim is not a barrier against direct host Docker administration or native app writes; activation must establish a stopped-service local state checkpoint and durable transaction journal before changing images. Do not use the claim on a live system until acceptance is complete.


### Stopped-state checkpoint and independent application availability

Routine core updates target only the two services in `aftergrid-core`: `core` and `worker`. Never stop optional application projects, remove the shared `aftergrid-apps` network, run a global Compose down, or copy unrelated data. The internal checkpoint primitive validates the exact stopped containers, reads the core data bind and named worker-state volume (a network-isolated, no-pull local helper mounts the latter read-only), refuses overlapping writable Docker binds and checks both SQLite databases and archive hashes. This is not exposed as a production command. A disposable guided CI scenario stops the two core services, checks the Kiwix reader during the outage and compares Kiwix/Kopia container IDs and start timestamps before and after. The local checkpoint includes private state; store it privately and do not treat it as a substitute for the independently verified Kopia recovery point. Native app activity may continue; avoid direct host changes during maintenance. The actual activation journal, restore and controlled replacement remain to be implemented.


### Disposable candidate replacement trial

Native acceptance exercises journaled Compose replacement using candidate references and copied core/worker state, leaving original persistent state authoritative. The trial uses only core/worker targets, no dependency recreation, no build/pull, and always returns to the previous images and original state even if the probe fails. The native fixture reuses the same image IDs under candidate tags to exercise replacement and state isolation; a unit test injects probe failure. This is acceptance-only, not production activation, promotion or crash recovery. Next: distinct reviewed release images, durable production promotion/source identity, native forced-failure acceptance, and a narrow browser update handoff.


### Distinct candidate and failed verification acceptance

The disposable fixture now creates distinct local candidate image IDs from the installed images with a harmless fixture label (not a separately released version), executes both a successful probe and an intentional native failed probe, and checks return to the exact original images and state without interrupting Kiwix/Kopia. A read-only `--trial-status CANDIDATE` reports journal phase and whether inspection is required; it never claims production activation. Candidate plans now bind core, worker and module source tree hashes plus Compose identity; changed or legacy unbound candidates must be prepared again. Source hashing does not establish a reproducible or signed build. Actual production promotion, crash reconciliation, and browser handoff remain gated.


### Interrupted disposable transaction reconciliation

The guided fixture now preserves candidate entrypoint/command/user/working-directory configuration (the earlier fixture overrode the entrypoint, so the distinct candidate startup failed). It also tests abrupt process exit after healthy candidate replacement using an isolated subprocess, then reconciles back to the original state with exact project, container, image and mount validation. The original maintenance hold must still match; unknown containers or state mounts fail closed. This remains a disposable-only procedure. Production promotion and reconciliation must separately define the authoritative state and installed source transition; do not run this on an installed host.


### Canonical promotion acceptance (disposable only)

Stage reviewed core/worker source trees on the installed filesystem. A journaled directory transition retains both original trees and reconciles interrupted renames by exact tree digests, refusing unknown paths. A successful completed isolated trial, matching original maintenance hold, fresh Kopia evidence and retained images are prerequisites for the disposable promotion. Stop only core/worker, capture a fresh local checkpoint, promote source, tag exact candidate images as the base Compose images and start against canonical original state mounts. Verify portal data and application availability, then recreate from base Compose to exercise persistence. The fixture adds a harmless source marker and distinct labeled local images, not a separately compiled release. The original source and pre-promotion state archives remain retained. If canonical startup or verification fails, journal inspection is required; automatic restoration of canonical databases and crash reconciliation are not implemented. No production activation command or browser control is enabled.


### Canonical promotion rollback (disposable only)

On a failed canonical startup or verification, the disposable promotion now attempts to stop only inspected core/worker services, revalidate the exact checkpoint and maintenance hold, restore the core bind from its private archive (retaining the failed directory), restore the named worker volume through the retained local worker image with a fixed offline helper, restore prior source and restart exact prior images. Failed worker state is retained in a private quarantine directory within the named volume; it is not automatically deleted. The native fixture deliberately adds a table to each canonical database then fails verification, checks that neither table survives rollback, verifies prior source/images, and checks application availability. Interrupted or failed restore is not automatically retried and remains held for inspection. Production activation remains disabled. The disposable fixture uses separate promotion directories; its previous success-directory collision was corrected.


### Dashboard and terminal maintenance release

The administrator dashboard now reports core update status and any host reconciliation requirement without exposing an activation control. The terminal disposable promotion/rollback path releases its update claim only after validating the recorded outcome, source transition, exact healthy running images and original matching maintenance hold. It returns to sealed maintenance, then normal recovery maintenance release is used. The current release boundary remains deliberate: no production activation, no automatic retry of a partially restored canonical state, no arbitrary host command interface. A release gate must require successful native promotion and schema rollback, a separately reviewed release build, interrupted canonical restoration acceptance, and a reviewed host execution/handoff. Existing application updates and recovery workflows remain independent.


### Resumable canonical restoration (disposable only)

Core restore now recognizes an interrupted directory rename and checks the extracted tree against the checkpoint before continuing. The worker restore helper records durable move/extract/complete phases inside its private quarantine and preserves partial extraction attempts. The internal resume function validates the promotion journal, configuration, checkpoint and matching hold before retrying restoration; it does not resume after prior startup begins, because the original services may already have changed state. The unit fixture interrupts the core directory rename and verifies idempotent restoration. Worker mid-restore interruption and prior-startup reconciliation still require native acceptance. Production release remains disabled.


### Appliance-first release boundary

Full hosted CI runs 45540553164, 45541062798 and 45541686525 passed, including native canonical activation and rollback of both modified databases, disconnected recovery and Compose lifecycle. Stop broadening updater architecture. Initial release should offer one manually approved reviewed update through a narrow, fixed execution mechanism. Reuse existing Compose and Kopia operations; no background updater service or arbitrary command API. The dashboard must distinguish ready, updating, succeeded, safely restored, and needs help in plain language. Keep optional applications running at their existing addresses. An ambiguous interrupted restore may stay safely held for documented operator/support recovery rather than requiring speculative automation; never release a hold without validated outcome. Actual release-build validation, narrow production authorization and browser action remain outstanding. Current native fixtures use distinct locally labeled images, not a published release.


### Source-built candidate startup acceptance

The update extractor keeps its outer source directory private (0700), but normalizes reviewed build-context files to 0644, executables to 0755 and inner directories to 0755. Docker COPY preserves these modes. Private mode 0600 for ordinary source files produced an image whose unprivileged core could not import app.py; fixture images made by relabeling installed containers did not expose that failure. Runtime data is outside the extraction allowlist, and special permission bits are not preserved.

On an explicitly designated Linux Docker test guest, run `AFTERGRID_CANDIDATE_BUILD_TEST=1 python3 -B tests/core_candidate_smoke.py CANDIDATE` after preparing a candidate. The runner reads source/ and candidate.json; a build-only build.json receipt is also supported for testing before live preparation admission. It starts a uniquely named native Compose project with fresh test data, no published ports, network none and no Docker socket. It checks exact images, embedded application source hashes, both health checks, first-run status, anonymous administrative refusal and native setup imports. It stops its two containers afterward, retains its private fixture/result for inspection and compares pre-existing container image/start/status identities. It does not activate the candidate, restore user data or test a production update. Production activation remains gated.


### Source-built promotion coverage and build metadata

The guided native fixture now archives only Compose and reviewed source trees, extracts them through the real updater and builds candidate images from those contexts. Its trial, forced failure, interrupted reconciliation, canonical schema rollback/resume and successful promotion paths use these source-built images rather than Docker-committed installed containers. The CI commit is supplied explicitly.

Candidate builds add and read back `org.opencontainers.image.revision`, `org.opencontainers.image.source` and `org.aftergrid.component` on the exact resulting image. Invalid commit/suffix values are refused before build; absent or mismatched labels refuse preparation. This metadata describes the requested build and does not authenticate a release. Production activation and browser execution remain gated.


### Tool packaging for independent execution

The existing worker image now includes core_update_tools.py and recovery_assets.py using its existing Python and Docker CLI. Top-level host commands keep their existing names through compatibility entry points. Tool packaging adds no service, privilege, host mount or update action, and does not enable activation. Native image checks load both CLIs with no network, read-only filesystem, dropped capabilities and no Docker socket or host binds. An independent executor still needs separate constrained dispatch and lifecycle acceptance.


### Detached core-only checkpoint executor acceptance

The exclusive guided CI fixture starts a detached container from the exact installed worker image, using its packaged fixed updater tools. The installation is mounted read-only at its original path, checkpoint output is a separate private writable sibling, and the helper has no network. Existing local Docker socket access is needed to run the reviewed core-only Compose operations; no host command API or production dispatch is exposed.

Both the normal path and an intentional post-checkpoint failure must recreate core and worker from their original image IDs, preserve the administrator session and maintenance hold, validate both checkpoint databases, and leave Kiwix/Kopia container IDs and start times unchanged while the reader stays accessible. The caller explicitly releases maintenance only afterward. This verifies the independent execution mechanism in disposable CI, not a production update or browser handoff.


### Detached canonical promotion acceptance fixture (native validation pending)

The disposable guided-recovery smoke now runs canonical candidate promotion in a detached container using the exact installed worker image. It checks successful promotion and an intentionally interrupted rollback, then uses the existing recovery command to resume restoration before releasing maintenance. Application identity and availability observations remain active while the executor runs.

The executor has no network, published ports, or administrator credentials. Its root filesystem is read-only; only the exact disposable install and candidate directories are writable, alongside the Docker socket required for replacement. This is acceptance tooling, and production activation remains disabled. Local Python compilation and seven focused candidate-build tests passed; Linux Docker acceptance is pending.
