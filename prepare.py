"""Build a versioned comparison of three HDB resale price measures."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import date
import hashlib
import json
import math
from pathlib import Path
import re
from statistics import median

import numpy as np

SOURCE = "https://data.gov.sg/datasets/d_8b84c4ee58e3cfc0ece0d773c8ca6abc/view"
MIN_CELL = 12
MIN_COVERAGE = 0.80
MIN_REGRESSION = 120
LEASE_PATTERN = re.compile(r"(\d+)\s+years?(?:\s+(\d+)\s+months?)?")
STOREY_PATTERN = re.compile(r"(\d+)\s+TO\s+(\d+)")
REQUIRED = {
    "month", "town", "flat_type", "floor_area_sqm", "flat_model",
    "remaining_lease", "storey_range", "resale_price",
}


def quarter(month: str) -> str:
    value = date.fromisoformat(month + "-01")
    return f"{value.year}-Q{(value.month - 1) // 3 + 1}"


def completed_quarter_labels(first: date, cutoff: date):
    year, month = first.year, (first.month - 1) // 3 * 3 + 1
    labels = []
    while True:
        start = date(year, month, 1)
        year, month = (year + 1, 1) if month == 10 else (year, month + 3)
        if date(year, month, 1) > cutoff:
            return labels
        labels.append(quarter(start.isoformat()[:7]))


def load(path: Path, cutoff: date):
    """Retain source row totals and report rejected rows by reason."""
    observations = defaultdict(list)
    rejected = Counter()
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if not REQUIRED <= set(reader.fieldnames or []):
            raise ValueError("Required columns are missing from the HDB CSV")
        for row in reader:
            try:
                month = date.fromisoformat(row["month"] + "-01")
                area = float(row["floor_area_sqm"])
                price = float(row["resale_price"])
                if not math.isfinite(area) or not math.isfinite(price) or min(area, price) <= 0:
                    raise ValueError("nonpositive or nonfinite")
            except (TypeError, ValueError):
                rejected["invalid month, price, or floor area"] += 1
                continue
            if month >= cutoff:
                rejected["month at or after cutoff"] += 1
                continue
            label, town, flat = quarter(row["month"]), row["town"].strip(), row["flat_type"].strip()
            if not town or not flat:
                rejected["missing stratum"] += 1
                continue
            lease, storey = LEASE_PATTERN.fullmatch(row["remaining_lease"].strip()), STOREY_PATTERN.fullmatch(row["storey_range"].strip())
            features = None
            if lease and storey:
                remaining = int(lease[1]) * 12 + int(lease[2] or 0)
                low, high = int(storey[1]), int(storey[2])
                if 0 < remaining <= 99 * 12 and 0 <= low <= high:
                    features = (math.log(area), remaining / 120, (low + high) / 20)
            observations[label].append((town, flat, price, features))
    return observations, rejected


def grouped_prices(rows):
    values = defaultdict(list)
    for town, flat, price, _ in rows:
        values[town, flat].append(price)
    return values


def stratum_step(reference_weights, earlier, later):
    older, newer = grouped_prices(earlier), grouped_prices(later)
    supported = {
        key for key in reference_weights
        if len(older[key]) >= MIN_CELL and len(newer[key]) >= MIN_CELL
    }
    weight = sum(reference_weights[key] for key in supported)
    coverage = weight / sum(reference_weights.values())
    if coverage < MIN_COVERAGE:
        return None, coverage, len(supported)
    weighted_log = sum(
        reference_weights[key] * math.log(median(newer[key]) / median(older[key]))
        for key in supported
    )
    return math.exp(weighted_log / weight), coverage, len(supported)


def hedonic_step(earlier, later):
    """Estimate the time effect from two quarters using common town/type levels."""
    earlier = [row for row in earlier if row[3] is not None]
    later = [row for row in later if row[3] is not None]
    towns = sorted({r[0] for r in earlier} & {r[0] for r in later})
    types = sorted({r[1] for r in earlier} & {r[1] for r in later})
    if not towns or not types:
        return None, 0
    allowed_towns, allowed_types = set(towns), set(types)
    older = [r for r in earlier if r[0] in allowed_towns and r[1] in allowed_types]
    newer = [r for r in later if r[0] in allowed_towns and r[1] in allowed_types]
    n = len(older) + len(newer)
    if min(len(older), len(newer)) < MIN_REGRESSION:
        return None, n
    rows = older + newer
    features = np.array([r[3] for r in rows])
    keep = features.std(axis=0) > 1e-8
    features = features[:, keep] - features[:, keep].mean(axis=0)
    cols = [np.ones(n), np.arange(n) >= len(older)]
    cols.extend(features.T)
    cols.extend(np.array([r[0] == town for r in rows]) for town in towns[1:])
    cols.extend(np.array([r[1] == flat for r in rows]) for flat in types[1:])
    matrix = np.column_stack(cols)
    log_price = np.log([r[2] for r in rows])
    estimate, _, rank, _ = np.linalg.lstsq(matrix, log_price, rcond=None)
    if rank < matrix.shape[1] or not np.isfinite(estimate[1]):
        return None, n
    return math.exp(estimate[1]), n


def rounded(value, digits=2):
    return round(value, digits) if value is not None else None


def segment_series(observations, labels, flat=None):
    groups = [[r for r in observations[label] if flat is None or r[1] == flat] for label in labels]
    if not groups[0]:
        return None
    weights = Counter((row[0], row[1]) for row in groups[0])
    basket = {key: count for key, count in weights.items() if count >= MIN_CELL}
    if not basket:
        return None
    base = median(row[2] for row in groups[0])
    mix = hedonic = 100.0
    points = []
    for i, (label, sample) in enumerate(zip(labels, groups, strict=True)):
        current = median(r[2] for r in sample) if sample else None
        coverage, matched, model_n = 1.0, len(basket), 0
        if i:
            mix_step, coverage, matched = stratum_step(basket, groups[i - 1], sample)
            h_step, model_n = hedonic_step(groups[i - 1], sample)
            mix = mix * mix_step if mix is not None and mix_step is not None else None
            hedonic = hedonic * h_step if hedonic is not None and h_step is not None else None
        points.append({
            "period": label,
            "n": len(sample),
            "medianSGD": rounded(current, 0),
            "raw": rounded(100 * current / base if current is not None else None),
            "mix": rounded(mix),
            "hedonic": rounded(hedonic),
            "basketCoverage": rounded(coverage, 4),
            "matchedStrata": matched,
            "modelN": model_n,
        })
    return {"name": flat or "All flat types", "baseStrata": len(basket), "points": points}


def release(source, cutoff, destination):
    data, rejected = load(source, cutoff)
    labels = completed_quarter_labels(date(2017, 1, 1), cutoff)
    if not labels or not all(data[key] for key in labels):
        raise ValueError("Missing a complete quarter. Confirm source and cutoff.")
    result = {
        "version": "1.0.0",
        "source": SOURCE,
        "sourceSHA256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "through": labels[-1],
        "sourceRowsIncluded": sum(len(data[key]) for key in labels),
        "incompleteQuarterRows": sum(len(group) for label, group in data.items() if label not in labels),
        "rejected": dict(rejected),
        "minimumStratum": MIN_CELL,
        "minimumCoverage": MIN_COVERAGE,
        "minimumRegressionQuarter": MIN_REGRESSION,
        "series": [
            value for flat in (None, "2 ROOM", "3 ROOM", "4 ROOM", "5 ROOM", "EXECUTIVE")
            if (value := segment_series(data, labels, flat)) is not None
        ],
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_suffix(".tmp")
    temp.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temp.replace(destination)
    print(f"{result['sourceRowsIncluded']} rows, {len(labels)} quarters, {len(result['series'])} series")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--cutoff", type=date.fromisoformat, required=True)
    parser.add_argument("--out", type=Path, default=Path("public/data.json"))
    args = parser.parse_args()
    release(args.source, args.cutoff, args.out)
