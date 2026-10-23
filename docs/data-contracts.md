# Person 1 data contracts (initial)

## Inventory

`data/sample/inventory.json` is the structural template. Unknown decisions use
JSON null; dataset status is `pending`, `available`, or `unavailable`.
Each required category has one entry: `dem`, `rainfall`, `land_cover`, `soil`,
`flood_evidence`. Combine multiple source files through a documented local
manifest if needed; the tool fingerprints only the file explicitly referenced.

Available entries require nonempty strings for source, local_path, format, CRS,
units, resolution, coverage and provenance. Record not-applicable values
explicitly with reasons. Metadata is self-reported; the tool does not parse GIS
files. Keep source URLs free of tokens. Provenance should include retrieval date,
license, processing history and observed/reanalysis/satellite provenance.

`study_area.bounds_wgs84`: [west, south, east, north] in decimal degrees.
Antimeridian-crossing bounds are unsupported. `analysis_crs` must be chosen for
the actual region. Historical event metadata records name, start, end and
 evidence_source; use ISO 8601 timestamps with explicit offsets. Timestamp parsing
and temporal/spatial overlap checks are not implemented yet.

## Future model handoff (design, not an implemented API)

Inputs: catchment identifier, rainfall totals in mm with interval/time zone,
terrain and classification references, model parameters and optional intervention.
Outputs must carry scenario ID, model version, timestamps, source fingerprints,
CRS, units, risk category, runoff quantities, spatial layer references and
uncertainty/assumption notes. Label observed data separately from model estimates.
GeoJSON exchange uses WGS84 longitude/latitude; numerical terrain analysis uses
a suitable metric CRS. Person 2 should agree on exact payloads before integration.
