"""Validate study inventories and fingerprint local inputs without modifying them."""

import argparse
import hashlib
import json
import math
from pathlib import Path

REQUIRED_KINDS = {"dem", "rainfall", "land_cover", "soil", "flood_evidence"}
STATUSES = {"pending", "available", "unavailable"}


def validate_inventory(inventory):
    """Check inventory structure using explicit metadata rules.

    Inputs: inventory, a decoded JSON object.
    Outputs: list of actionable error strings; empty means structurally valid,
        not scientifically verified or ready for modelling.
    """
    errors = []
    if not isinstance(inventory, dict):
        return ["Inventory must be a JSON object."]
    area = inventory.get("study_area")
    if not isinstance(area, dict):
        errors.append("study_area must be an object.")
    else:
        bounds = area.get("bounds_wgs84")
        if bounds is not None:
            if (not isinstance(bounds, list) or len(bounds) != 4
                    or any(isinstance(v, bool) or not isinstance(v, (int, float))
                           or not math.isfinite(v) for v in bounds)):
                errors.append("bounds_wgs84 must contain four finite numbers.")
            else:
                west, south, east, north = bounds
                if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
                    errors.append("Bounds must be ordered west, south, east, north; antimeridian areas are unsupported.")
    datasets = inventory.get("datasets")
    if not isinstance(datasets, list):
        return errors + ["datasets must be a list."]
    seen = set()
    for index, dataset in enumerate(datasets):
        label = f"datasets[{index}]"
        if not isinstance(dataset, dict):
            errors.append(f"{label} must be an object.")
            continue
        kind = dataset.get("kind")
        if not isinstance(kind, str) or kind not in REQUIRED_KINDS:
            errors.append(f"{label}: unsupported kind.")
        elif kind in seen:
            errors.append(f"{label}: duplicate kind {kind}.")
        else:
            seen.add(kind)
        status = dataset.get("status")
        if not isinstance(status, str) or status not in STATUSES:
            errors.append(f"{label}: invalid status.")
        if status == "available":
            for field in ("source", "local_path", "format", "crs", "units", "resolution", "coverage", "provenance"):
                if not isinstance(dataset.get(field), str) or not dataset[field].strip():
                    errors.append(f"{label}: available data requires {field}.")
    for kind in sorted(REQUIRED_KINDS - seen):
        errors.append(f"Missing dataset entry: {kind}.")
    return errors


def fingerprint_file(root, relative_path):
    """Read a contained local file in chunks and calculate its SHA-256.

    Inputs: root directory and relative_path string beneath it.
    Outputs: dictionary with relative path, byte size and hexadecimal digest.
        Raises ValueError for unsafe paths and OSError for unreadable files.
    """
    root = Path(root).resolve()
    if not isinstance(relative_path, str) or not relative_path.strip():
        raise ValueError("A nonempty relative file path is required.")
    candidate = Path(relative_path)
    if candidate.is_absolute():
        raise ValueError("Absolute dataset paths are not allowed.")
    path = (root / candidate).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Dataset path escapes the data root.")
    if not path.is_file():
        raise ValueError(f"Dataset is not a regular file: {relative_path}")
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
    return {"path": relative_path, "size_bytes": size, "sha256": digest.hexdigest()}


def build_report(inventory, data_root):
    """Combine metadata checks with checksums for available local datasets.

    Inputs: decoded inventory and trusted local data_root directory.
    Outputs: report dictionary with errors, pending decisions and file records.
        File failures are reported explicitly; no dataset contents are altered.
    """
    errors = validate_inventory(inventory)
    pending = []
    files = []
    if not errors:
        area = inventory["study_area"]
        for field in ("name", "bounds_wgs84", "analysis_crs"):
            if not area.get(field):
                pending.append(f"Select study_area.{field}.")
        event = inventory.get("historical_event")
        if not isinstance(event, dict) or any(not event.get(k) for k in ("name", "start", "end", "evidence_source")):
            pending.append("Select and document a historical flood event and evidence source.")
        for dataset in inventory["datasets"]:
            if dataset["status"] != "available":
                pending.append(f"Acquire or document missing {dataset['kind']} data.")
                continue
            try:
                files.append({"kind": dataset["kind"], **fingerprint_file(data_root, dataset["local_path"])})
            except (OSError, ValueError) as exc:
                errors.append(f"{dataset['kind']}: {exc}")
    return {"errors": errors, "pending": pending, "files": files,
            "geospatial_verification": "Not performed: inspect raster metadata, CRS, coverage and event alignment separately."}


def main():
    """Run the inventory CLI using JSON input and print a JSON report.

    Inputs: command-line inventory path and optional --data-root directory.
    Outputs: process status 0 for complete metadata/file checks, 1 for invalid
        inputs, or 2 for pending decisions/data. Never certifies model readiness.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory", type=Path)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    args = parser.parse_args()
    try:
        inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
        report = build_report(inventory, args.data_root)
    except (OSError, ValueError) as exc:
        print(json.dumps({"errors": [str(exc)]}))
        return 1
    print(json.dumps(report, indent=2))
    return 1 if report["errors"] else 2 if report["pending"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
