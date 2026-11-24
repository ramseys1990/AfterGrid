# Optional modules

Kiwix, Homebox, Grocy and Kopia are optional Compose modules. No optional services are installed with the core. Kiwix passed hosted lifecycle CI; the other three require runtime validation.

Use a standard Compose file and minimal module.yaml (currently JSON-formatted YAML for dependency-free reading). Only reviewed definitions are available to the worker. Keep content and state separate; never remove volumes by default.

Offline maps is an independent optional module with local PMTiles/MBTiles archive serving. See [Maps](maps/README.md). It installs no geographic data by default.
