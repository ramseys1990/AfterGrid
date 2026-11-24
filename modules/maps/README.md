# Offline maps

This optional module runs the upstream lightweight TileServer GL container with its bundled browser previews and local tile endpoints. It starts with an explicit configuration and no required archive; missing archive slots are skipped instead of using the upstream automatic demo download.

## Use

Install Offline maps in the AfterGrid application catalog. On LAN installations open the card link on port 8084. No sign-in is required by the map viewer itself. Only share on a trusted LAN; the map files may contain sensitive information. Never port-forward the service to the internet.

Copy a trusted, licensed local archive into /opt/aftergrid/content/maps:
- region.pmtiles (PMTiles)
- region.mbtiles (MBTiles)

Keep the original source and attribution. Ensure the file and directory are readable by the service. Copy to a temporary name and rename only when complete. Restart the Maps module using the portal. Open the native browser preview. One archive of each type is supported initially; empty installation is valid and no map data is included. Raster archives provide a rendered map; vector archives provide a data inspection view, not a complete cartographic navigation experience. The source archive determines coverage, zoom levels and attribution. The viewer and tile endpoints are served locally.

The module never mounts the Docker socket or writes map content. Uninstall preserves the map directory. Software and data are independent. Operators can use the upstream [PMTiles CLI](https://docs.protomaps.com/pmtiles/cli) to prepare regional extracts elsewhere, or obtain appropriately licensed MBTiles. Do not bulk scrape public OpenStreetMap tile servers.

## Next

Regional selection and downloads with progress/storage estimates; a complete labeled basemap and local glyphs/sprites; waypoint and GPX/KML tools; independent Valhalla routing data and UI. No road routing is available in this milestone. Actual browser behavior with the WAN disconnected, local map attribution, and hardware performance remain to be tested. Hosted CI exercises a small pinned upstream PMTiles fixture and the normal module lifecycle.

## Regional extracts

The admin portal can estimate and extract a selected bounding box from a published Protomaps build. Use the official builds list for the date. Maximum zoom 15; development cap 4 GiB, with extra space reserved. The CLI downloads only relevant ranges. Estimate and actual size can differ. The file is published only after native structural verification; this does not prove every tile's checksum. The existing PMTiles slot is never overwritten. Interrupted jobs require a new estimate; no resume or automatic replacement yet. Restart Maps to use the result. Preserve OpenStreetMap attribution and the source date. For old installations, change ownership of the content/maps directory to UID/GID 10001 (not the whole server). Actual internet extraction and offline browser acceptance remain pending.

## Styled viewer

Use the Maps card's styled viewer to render compatible Protomaps MVT and raster PMTiles in the browser. The core serves the same archive via byte ranges, not a second copy. All JS, CSS, glyphs and sprites are bundled at image build. English labels are the initial style; unsupported vector schemas and MBTiles use the native tile viewer. No runtime CDN requests are needed. The public map archive is accessible on the trusted LAN after initial setup. Only store maps intended for sharing. Preserve source attribution. Browser/WebGL and actual vector labels remain to be validated.

The region picker uses a small bundled Natural Earth public-domain land outline, even with no map downloaded. Drag between two corners or choose an approximate regional preset; edit the coordinates for precision. The overview is not a road map. Keep the original download estimate and explicit confirmation steps.
