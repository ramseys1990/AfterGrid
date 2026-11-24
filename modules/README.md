# Optional modules

Kiwix is the first implemented Compose module. No optional services are installed with the core. Homebox, Grocy and Kopia are next.

Use a standard Compose file and minimal module.yaml (currently JSON-formatted YAML for dependency-free reading). Only reviewed definitions are available to the worker. Keep content and state separate; never remove volumes by default.
