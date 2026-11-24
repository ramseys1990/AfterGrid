# Mesh / TAK interoperability review

AfterGrid currently installs MeshMonitor and MicroTAK independently. They do not automatically exchange messages or location records.

MeshMonitor's native ATAK/CoT features already provide a candidate interface for mesh data; see https://meshmonitor.org/blog/2026-07-27-v4.13.2-release.html and upstream configuration documentation. Its separate feed has different access-control properties from MicroTAK. AfterGrid intentionally does not publish the feed port or enable it, and does not expose unauthenticated CoT or forward private positions by default. Native Meshtastic client-side TAK support is another candidate: https://meshtastic.org/docs/software/integrations/integrations-atak-plugin/.

Decision: do not create a new protocol translator or enable an automatic server-to-server bridge until there is a reviewed, authenticated native connection method. Validate with authorized test radios and consenting clients on a trusted LAN. Document source/destination scope, permissions, duplicate/loop prevention, offline behavior, and explicit opt-in before accepting any bridge. No hardware tests or bridge functionality are claimed by this review.
