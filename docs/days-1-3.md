# Person 1: Days 1–3

## Scope and current status

Source: supplied `from_page_32_to_end.pdf`, final two-person implementation plan.
Only Person 1 work is implemented here. Backend, frontend, map UI, scheduled
fetching and application integration belong to Person 2 and are not included.
No city, catchment, historical event or real input dataset has been selected or
verified. The template is a checklist, not synthetic geographical data.

## Architecture

```text
Source files + recorded provenance
           ↓
Inventory metadata validation → safe local file inspection + SHA-256
           ↓
Manual scientific checks (CRS, units, coverage, timing, resolution)
           ↓
Future: terrain → runoff → event risk → validation → interventions
           ↓
Person 2 consumes documented model outputs
```

## Task board

| Day | Person 1 task | State / acceptance evidence |
| --- | --- | --- |
| 1 | Define flood scope and minimum inputs | Documented below; geographic scope awaits user decision |
| 1 | Research candidate data sources | Source shortlist below; availability not verified |
| 2 | Compare candidate catchments | Pending candidate selection and evidence review |
| 2 | Verify DEM, rainfall, land cover, soil and event evidence | Pending actual datasets |
| 3 | Acquire and inspect inputs | Local metadata/checksum tool implemented; acquisition pending |
| 3 | Check CRS, overlap and event timing | Manual checklist documented; not yet performed |

## Selection procedure

Choose 2–3 candidate urban catchments, not entire cities by default. For each,
record boundary, terrain resolution, rainfall period/time step, documented flood
locations or polygons, source access restrictions, and missing soil/land-cover
information. Prefer a manageable hydrological catchment with independently
recorded flood evidence. Administrative clipping alone may exclude upstream flow.
Do not pick the region based only on proximity or map appearance.

## Minimum inputs and source shortlist

These are candidate sources from the PDF, not confirmed downloads or guarantees.

| Input | Candidate source | Required checks |
| --- | --- | --- |
| DEM | Copernicus DEM / SRTM | horizontal/vertical datum, metres, nodata, resolution and upstream coverage |
| Event rainfall | ERA5/Open-Meteo Archive, GPM IMERG, available gauges | accumulated mm vs rate, UTC/time zone, interval and gaps |
| Land cover | ESA WorldCover | classification legend, date, resolution, reprojection method |
| Soil | SoilGrids / documented soil maps | units, depth, uncertainty; hydrologic soil groups need justified derivation |
| Flood evidence | authority reports, documented locations, satellite flood extent | event date, source references, positional uncertainty, observation coverage |
| Drainage (optional initially) | OpenStreetMap / municipal records | incomplete coverage, surveyed versus assumed dimensions |

Rainfall reanalysis is not a gauge measurement or an archived operational
forecast. Preserve these distinctions in provenance. Lack of drainage dimensions
prevents defensible hydraulic capacity claims; do not fill gaps silently.

## Acquisition and inspection workflow

1. Select the region and event with the user; record source/license and retrieval date.
2. Download from the source using its documented procedure; keep originals in
   `data/raw/`. This environment cannot directly access the listed data portals.
   No automatic downloader or fabricated fallback has been provided.
3. Populate the inventory. Use `unavailable` for confirmed missing data and
   document its reason in provenance; use `pending` when not checked.
4. Run the inventory CLI. It reads files without modifying them, checks required
   metadata and calculates SHA-256 in bounded-memory chunks. Absolute paths,
   paths outside the configured root, and escaping symlinks are rejected.
5. Inspect rasters in QGIS or a later Rasterio tool. Confirm actual metadata
   matches the inventory, catchment coverage, nodata, elevation units, land-cover
   legend and soil interpretation. A filename or checksum cannot prove these.
6. Use WGS84 longitude/latitude for exchange boundaries. Select an appropriate
   local metric projected CRS after region selection; never calculate slope,
   distance or area directly in geographic degrees.
7. Align rainfall intervals with the event and flood evidence. Log missing values
   instead of treating them as zero. Confirm all layers cover the model domain.
8. Record the validation plan and hand the verified inventory to Person 2.

## Scientific constraints for later work

Preserve original DEM depressions before conditioning; real storage must not be
indiscriminately filled. Curve Number assumptions require soil/land-cover and
antecedent-moisture justification. Terrain-based risk is not calibrated depth.
A single event used for tuning and scoring is a consistency check, not independent
validation. Flooded points alone do not establish a comprehensive false-alarm rate.

## Decisions required to finish Day 3

- City/catchment boundary and acceptable model scale.
- Historical flood event, rainfall period and independently sourced observations.
- Actual input files and licensing/access restrictions.
- Local analysis CRS and accepted missing-data assumptions.

Only after those decisions and checks can the Day 3 data milestone be marked complete.
