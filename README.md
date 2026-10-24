# Climate-Resilient Urban Water Management

Person 1 workspace: geospatial inputs, hydrology, flood-risk simulation,
validation and intervention calculations. Current work covers the **Days 1–3
preparation tools**, not a completed data-acquisition milestone.

## Run (Python 3.10+, no runtime dependencies)

```sh
python -m unittest discover -s tests -v
python -m simulation.inventory data/sample/inventory.json --data-root data
```

The supplied inventory intentionally returns exit status **2**: the region,
historical event and real datasets are not yet selected. Status 1 means invalid
metadata or unreadable/unsafe input; status 0 means metadata and file checks
completed, **not** scientific or geospatial approval.

Copy the inventory to your own project configuration, populate its metadata,
and put real inputs under ignored `data/raw/`. Paths are relative to `--data-root`.
Do not commit large datasets, credentials or private infrastructure information.

See [Days 1–3 plan and methods](docs/days-1-3.md),
[data contracts](docs/data-contracts.md), and [engineering rules](AGENTS.md).
