# Household organization

The family shares one AfterGrid portal, one Homebox instance and one Grocy instance. Household records are organization labels, not accounts or permission boundaries. Native application security remains independent.

Create household names in the portal as administrator. In Homebox or Grocy, create native locations using the app's own UI. Enter the corresponding native location ID and descriptive label in AfterGrid. Homebox uses UUIDs; Grocy uses numeric location IDs. References are entered manually and not yet checked against a live application. An owning household and physical storage household may differ, or either may be left shared/unassigned. These are location-level defaults, not assertions that every item in that location belongs to the same household.

All LAN portal visitors can view and filter the directory. Only the administrator can change it. Do not store private household details in labels. Deleting a reference never deletes native stock, equipment, locations, or labels. A referenced household must be reassigned or unlinked before deletion.

The next slice is native read-only API location discovery and live inventory summaries. Stock quantities, units, item-level ownership, mixed ownership and native account/API access need explicit validation. The current directory works offline and needs no inventory service running.
