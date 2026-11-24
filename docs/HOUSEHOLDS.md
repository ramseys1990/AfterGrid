# Household organization

The family shares one AfterGrid portal, one Homebox instance and one Grocy instance. Household records are organization labels, not accounts or permission boundaries. Native application security remains independent.

Create household names in the portal as administrator. In Homebox or Grocy, create native locations using the app's own UI. Enter the corresponding native location ID and descriptive label in AfterGrid. Homebox uses UUIDs; Grocy uses numeric location IDs. References are entered manually and not yet checked against a live application. An owning household and physical storage household may differ, or either may be left shared/unassigned. These are location-level defaults, not assertions that every item in that location belongs to the same household.

All LAN portal visitors can view and filter the directory. Only the administrator can change it. Do not store private household details in labels. Deleting a reference never deletes native stock, equipment, locations, or labels. A referenced household must be reassigned or unlinked before deletion.

The next slice is native read-only API location discovery and live inventory summaries. Stock quantities, units, item-level ownership, mixed ownership and native account/API access need explicit validation. The current directory works offline and needs no inventory service running.

## Native discovery and location reports

Create a dedicated API key in each native application and paste it into the administrator connection form. Homebox uses Bearer authentication and its v0.27.1 entity tree; Grocy uses GROCY-API-KEY and v4.7.1 location/stock endpoints. The keys may carry broader native privileges than AfterGrid uses. AfterGrid stores them in the private core SQLite file; protect backups and revoke keys in the native apps when necessary. Disconnect forgets the saved key only. The core makes fixed GET requests on the existing private app network; it never writes inventory.

Select a discovered location to fill the mapping form. Live inventory on a mapped location shows Homebox item records (not quantity, and excludes child locations) or Grocy amounts by product and native stock unit. No incompatible units are summed. These reports require portal administrator login for now; the directory remains shared. No background syncing or cache; if an app is unavailable, report an error, not zero stock. API behavior is based on the pinned upstream contracts; a real authenticated integration test remains outstanding.

## Consolidated inventory (0.7.3-dev)

Administrators can request one live view across mapped locations, filtered independently by owning household or physical storage household, including shared/unassigned. Each page reads up to eight mappings, reusing native location and product metadata within that request. Homebox counts direct item records only; totals apply only to available locations on the current page. Grocy quantities stay grouped by native product and unit within each location. No cross-product or cross-unit totals. Failed/disconnected native services are reported separately from empty locations. Reports are not stored, do not expose keys and do not change native inventory. Refresh after changing mappings or reconnecting; each page is a separate live read rather than a transactional snapshot. Family-facing access and native authenticated API acceptance remain outstanding.
