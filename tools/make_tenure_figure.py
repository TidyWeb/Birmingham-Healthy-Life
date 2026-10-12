#!/usr/bin/env python3
"""Build the HLE and social-renting comparison figure and its numbers CSV."""

from __future__ import annotations

import csv
import io
import json
import os
import sys
from pathlib import Path
from urllib.request import Request, urlopen
from zipfile import ZipFile
from io import BytesIO

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.patches import Patch, Rectangle
except ImportError as exc:
    raise SystemExit(
        "This script needs NumPy and Matplotlib in the active Python environment."
    ) from exc


# Read the durable project sources directly; set BIRMINGHAM_HLE_PROJECT_ROOT to relocate them.
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROJECT_ROOT = Path(
    "/home/Phil/C_C/Learn_Python_Data/Working Files/Unit 2/MAIN_PROJECT/Birmingham HLE"
)
PROJECT_ROOT = Path(
    os.environ.get("BIRMINGHAM_HLE_PROJECT_ROOT", str(DEFAULT_PROJECT_ROOT))
).expanduser()

# These are the source files: hle_2019_2023_msoa.csv and
# ons_msoa21_boundaries_exploratory_west_midlands.geojson.
HLE_SOURCE = PROJECT_ROOT / "Data/Cleaned/HLE/hle_2019_2023_msoa.csv"
BOUNDARY_SOURCE = (
    PROJECT_ROOT
    / "Data/Raw/Geography/ons_msoa21_boundaries_exploratory_west_midlands.geojson"
)

# Read census2021-ts054-msoa.csv directly from the official Nomis bulk archive.
TENURE_ARCHIVE_URL = "https://www.nomisweb.co.uk/output/census/2021/census2021-ts054.zip"
TENURE_MEMBER = "census2021-ts054-msoa.csv"

FIGURE_PATH = REPO_ROOT / "assets/img/tenure-hle.webp"
NUMBERS_PATH = REPO_ROOT / "tools/tenure_hle_numbers.csv"

TEXT = "#18262e"
SECONDARY = "#4b5b62"
WHITE = "#ffffff"

HLE_BAND_EDGES = (55.0, 60.0, 65.0, 70.0)
HLE_BAND_LABELS = ("<55", "55–<60", "60–<65", "65–<70", "≥70")
HLE_BAND_COLOURS = ("#46327e", "#365c8d", "#21918c", "#5ec962", "#d7e75b")
RENT_QUINTILE_COLOURS = ("#fff7bc", "#fec44f", "#fe9929", "#ec7014", "#cc4c02")
BIVARIATE_COLOURS = (
    ("#e8e8e8", "#e4acac", "#c85a5a"),
    ("#b0d5df", "#ad9ea5", "#985356"),
    ("#64acbe", "#627f8c", "#574249"),
)


def read_hle_values():
    """Average male and female HLE for each MSOA, as the dashboard does."""
    if not HLE_SOURCE.is_file():
        raise FileNotFoundError(
            f"Could not find {HLE_SOURCE}. Set BIRMINGHAM_HLE_PROJECT_ROOT to the project root."
        )

    by_area = {}
    with HLE_SOURCE.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        required = {"area_code", "sex", "hle_years"}
        if not required.issubset(reader.fieldnames or ()):
            raise ValueError(f"{HLE_SOURCE} does not contain the expected HLE columns.")

        for row in reader:
            by_area.setdefault(row["area_code"], {})[row["sex"]] = float(row["hle_years"])

    result = {}
    for code, values in by_area.items():
        if set(values) != {"Male", "Female"}:
            raise ValueError(f"{code} does not have both male and female HLE values.")
        result[code] = (values["Male"] + values["Female"]) / 2

    return result


def read_tenure_values():
    """Download the public TS054 source and calculate social rent as a household share."""
    request = Request(TENURE_ARCHIVE_URL, headers={"User-Agent": "HLE-tenure-figure/1.0"})
    with urlopen(request, timeout=60) as response:
        archive_bytes = response.read()

    with ZipFile(BytesIO(archive_bytes)) as archive:
        with archive.open(TENURE_MEMBER) as source:
            text_source = io.TextIOWrapper(source, encoding="utf-8-sig", newline="")
            reader = csv.DictReader(text_source)
            required = {
                "geography code",
                "Tenure of household: Total: All households",
                "Tenure of household: Social rented",
            }
            if not required.issubset(reader.fieldnames or ()):
                raise ValueError("The Nomis TS054 MSOA CSV has unexpected columns.")

            result = {}
            for row in reader:
                code = row["geography code"]
                total = int(row["Tenure of household: Total: All households"])
                social_rent = int(row["Tenure of household: Social rented"])
                if total <= 0:
                    raise ValueError(f"{code} has no occupied households in TS054.")
                result[code] = 100 * social_rent / total

    return result


def read_boundaries():
    """Load the 660 MSOA21 polygons used by the dashboard."""
    if not BOUNDARY_SOURCE.is_file():
        raise FileNotFoundError(
            f"Could not find {BOUNDARY_SOURCE}. Set BIRMINGHAM_HLE_PROJECT_ROOT to the project root."
        )

    with BOUNDARY_SOURCE.open("r", encoding="utf-8") as source:
        feature_collection = json.load(source)

    features = feature_collection.get("features", [])
    if not features:
        raise ValueError(f"{BOUNDARY_SOURCE} contains no GeoJSON features.")
    return features


def pearson_correlation(left, right):
    """Return Pearson correlation without adding a statistics-library dependency."""
    left_centered = left - left.mean()
    right_centered = right - right.mean()
    denominator = np.sqrt(np.dot(left_centered, left_centered) * np.dot(right_centered, right_centered))
    return float(np.dot(left_centered, right_centered) / denominator)


def average_ranks(values):
    """Assign average ranks to ties for a standard Spearman rank correlation."""
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values), dtype=float)
    start = 0

    while start < len(values):
        stop = start + 1
        while stop < len(values) and values[order[stop]] == values[order[start]]:
            stop += 1
        ranks[order[start:stop]] = (start + 1 + stop) / 2
        start = stop

    return ranks


def correlation(left, right):
    """Calculate Pearson and tie-aware Spearman correlations."""
    pearson = pearson_correlation(left, right)
    spearman = pearson_correlation(average_ranks(left), average_ranks(right))
    return spearman, pearson


def quantile_edges(values, quantiles):
    """Get reproducible linear-interpolated quantile boundaries."""
    return np.quantile(np.asarray(values, dtype=float), quantiles, method="linear")


def classify(values, edges):
    """Assign low-to-high class indexes, sending a value on a cut to the higher class."""
    return np.searchsorted(np.asarray(edges)[1:-1], values, side="right")


def fmt(value, places=2):
    return f"{float(value):.{places}f}"


def write_numbers_csv(
    area_count,
    spearman,
    pearson,
    rent_quintile_edges,
    hle_tertile_edges,
    rent_tertile_edges,
    cell_counts,
    diagonal_count,
):
    """Write every requested statistic and class count to the named CSV."""
    fields = (
        "record_type",
        "measure",
        "statistic",
        "value",
        "category",
        "lower_bound",
        "upper_bound",
        "social_rent_tertile",
        "hle_tertile",
        "count",
        "percentage",
    )
    rows = [
        {
            "record_type": "summary",
            "measure": "all areas",
            "statistic": "n",
            "value": area_count,
        },
        {
            "record_type": "summary",
            "measure": "social_rent_share_percent and hle_average_years",
            "statistic": "spearman",
            "value": spearman,
        },
        {
            "record_type": "summary",
            "measure": "social_rent_share_percent and hle_average_years",
            "statistic": "pearson",
            "value": pearson,
        },
    ]

    for index, edge in enumerate(rent_quintile_edges):
        percentile = (0, 20, 40, 60, 80, 100)[index]
        rows.append(
            {
                "record_type": "quintile_break",
                "measure": "social_rent_share_percent",
                "statistic": "boundary",
                "value": edge,
                "category": f"{percentile}th percentile",
            }
        )

    for measure, edges in (
        ("hle_average_years", hle_tertile_edges),
        ("social_rent_share_percent", rent_tertile_edges),
    ):
        for index, edge in enumerate(edges):
            percentile = (0, 100 / 3, 200 / 3, 100)[index]
            rows.append(
                {
                    "record_type": "tertile_break",
                    "measure": measure,
                    "statistic": "boundary",
                    "value": edge,
                    "category": f"{percentile:.2f}th percentile",
                }
            )

    rent_names = ("low", "mid", "high")
    hle_names = ("high", "mid", "low")
    for rent_index, rent_name in enumerate(rent_names):
        for column_index, hle_name in enumerate(hle_names):
            count = int(cell_counts[rent_index, column_index])
            rows.append(
                {
                    "record_type": "bivariate_cell",
                    "measure": "area count",
                    "statistic": "count",
                    "category": f"social_rent_{rent_name}__hle_{hle_name}",
                    "social_rent_tertile": rent_name,
                    "hle_tertile": hle_name,
                    "count": count,
                    "percentage": 100 * count / area_count,
                }
            )

    rows.append(
        {
            "record_type": "summary",
            "measure": "bivariate map",
            "statistic": "diagonal_percentage",
            "value": 100 * diagonal_count / area_count,
            "category": "social rent low with HLE high; mid with mid; high with low",
            "count": diagonal_count,
            "percentage": 100 * diagonal_count / area_count,
        }
    )

    with NUMBERS_PATH.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def mercator_xy(longitudes, latitudes):
    """Project WGS84 longitude and latitude so every map uses the same scale."""
    earth_radius = 6378137.0
    safe_latitudes = np.clip(latitudes, -85.0, 85.0)
    x = earth_radius * np.deg2rad(longitudes)
    y = earth_radius * np.log(np.tan(np.pi / 4 + np.deg2rad(safe_latitudes) / 2))
    return x, y


def polygon_rings(feature):
    """Yield exterior rings for Polygon and MultiPolygon MSOA geometries."""
    geometry = feature["geometry"]
    polygons = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
    for polygon in polygons:
        yield polygon[0]


def projected_bounds(features):
    """Find one shared map extent from the same 660 boundaries."""
    bounds = []
    for feature in features:
        for ring in polygon_rings(feature):
            coordinates = np.asarray(ring, dtype=float)
            x, y = mercator_xy(coordinates[:, 0], coordinates[:, 1])
            bounds.append((x.min(), y.min(), x.max(), y.max()))

    return (
        min(bound[0] for bound in bounds),
        min(bound[1] for bound in bounds),
        max(bound[2] for bound in bounds),
        max(bound[3] for bound in bounds),
    )


def style_map_axis(axis, extent):
    """Apply identical bounds, scale, and white background to every map."""
    xmin, ymin, xmax, ymax = extent
    x_pad = (xmax - xmin) * 0.012
    y_pad = (ymax - ymin) * 0.012
    axis.set_facecolor(WHITE)
    axis.set_xlim(xmin - x_pad, xmax + x_pad)
    axis.set_ylim(ymin - y_pad, ymax + y_pad)
    axis.set_aspect("equal", adjustable="box")
    axis.set_xticks([])
    axis.set_yticks([])
    for spine in axis.spines.values():
        spine.set_visible(False)


def draw_area_map(axis, features, color_by_code):
    """Draw the area polygons with the requested thin white boundaries."""
    for feature in features:
        code = feature["properties"]["MSOA21CD"]
        color = color_by_code[code]
        for ring in polygon_rings(feature):
            coordinates = np.asarray(ring, dtype=float)
            x, y = mercator_xy(coordinates[:, 0], coordinates[:, 1])
            axis.fill(
                x,
                y,
                facecolor=color,
                edgecolor=WHITE,
                linewidth=0.2,
                antialiased=True,
            )


def add_map_legend(axis, colours, labels, title):
    """Place a compact, unit-labelled legend directly below a top-row map."""
    axis.set_facecolor(WHITE)
    axis.set_axis_off()
    handles = [
        Patch(facecolor=colour, edgecolor="none", label=label)
        for colour, label in zip(colours, labels)
    ]
    legend = axis.legend(
        handles=handles,
        title=title,
        ncol=5,
        loc="center",
        mode="expand",
        frameon=False,
        fontsize=7.2,
        title_fontsize=8,
        handlelength=1.0,
        handleheight=0.8,
        columnspacing=0.9,
        borderaxespad=0,
    )
    legend.get_title().set_color(SECONDARY)
    for label in legend.get_texts():
        label.set_color(SECONDARY)


def draw_bivariate_legend(axis):
    """Show the 3 by 3 colour key in the same orientation used on map 3."""
    axis.set_facecolor(WHITE)
    axis.set_aspect("equal", adjustable="box")
    axis.set_xlim(-0.15, 3.15)
    axis.set_ylim(-0.58, 3.38)
    axis.set_xticks([])
    axis.set_yticks([])
    for spine in axis.spines.values():
        spine.set_visible(False)

    for rent_index in range(3):
        for hle_column in range(3):
            axis.add_patch(
                Rectangle(
                    (hle_column, rent_index),
                    1,
                    1,
                    facecolor=BIVARIATE_COLOURS[rent_index][hle_column],
                    edgecolor=WHITE,
                    linewidth=0.8,
                )
            )

    axis.text(
        1.5,
        3.18,
        "More social renting ↑",
        ha="center",
        va="center",
        color=SECONDARY,
        fontsize=8.5,
    )
    axis.text(
        1.5,
        -0.34,
        "Lower HLE →",
        ha="center",
        va="center",
        color=SECONDARY,
        fontsize=8.5,
    )


def make_figure(
    features,
    hle_values,
    rent_values,
    hle_band_classes,
    rent_quintile_classes,
    hle_tertile_classes,
    rent_tertile_classes,
    rent_quintile_edges,
    spearman,
    cell_counts,
    diagonal_percentage,
):
    """Render the two top maps and the larger bivariate map underneath."""
    plt.rcParams.update({"font.family": "DejaVu Sans", "axes.unicode_minus": False})

    figure = plt.figure(figsize=(12, 10), facecolor=WHITE)
    outer = figure.add_gridspec(
        2,
        1,
        height_ratios=(1.0, 1.16),
        left=0.04,
        right=0.96,
        top=0.875,
        bottom=0.055,
        hspace=0.12,
    )
    top = outer[0].subgridspec(
        2,
        2,
        height_ratios=(1.0, 0.17),
        wspace=0.045,
        hspace=0.015,
    )
    bottom = outer[1].subgridspec(
        2,
        2,
        height_ratios=(1.0, 0.12),
        width_ratios=(4.4, 1.2),
        wspace=0.035,
        hspace=0.015,
    )

    hle_axis = figure.add_subplot(top[0, 0])
    rent_axis = figure.add_subplot(top[0, 1])
    hle_legend_axis = figure.add_subplot(top[1, 0])
    rent_legend_axis = figure.add_subplot(top[1, 1])
    bivariate_axis = figure.add_subplot(bottom[0, 0])
    bivariate_legend_axis = figure.add_subplot(bottom[0, 1])
    agreement_axis = figure.add_subplot(bottom[1, :])

    extent = projected_bounds(features)
    for axis in (hle_axis, rent_axis, bivariate_axis):
        style_map_axis(axis, extent)

    codes = [feature["properties"]["MSOA21CD"] for feature in features]
    hle_colours = {
        code: HLE_BAND_COLOURS[int(hle_band_classes[index])]
        for index, code in enumerate(codes)
    }
    rent_colours = {
        code: RENT_QUINTILE_COLOURS[int(rent_quintile_classes[index])]
        for index, code in enumerate(codes)
    }

    # Grid rows rise from low to high social rent; columns move from high to low HLE.
    bivariate_colours = {}
    for index, code in enumerate(codes):
        rent_row = int(rent_tertile_classes[index])
        hle_column = 2 - int(hle_tertile_classes[index])
        bivariate_colours[code] = BIVARIATE_COLOURS[rent_row][hle_column]

    draw_area_map(hle_axis, features, hle_colours)
    draw_area_map(rent_axis, features, rent_colours)
    draw_area_map(bivariate_axis, features, bivariate_colours)

    hle_axis.set_title(
        "Healthy life expectancy, 2019–2023",
        loc="left",
        color=TEXT,
        fontsize=10.5,
        fontweight="bold",
        pad=4,
    )
    rent_axis.set_title(
        "Households in social rent, Census 2021",
        loc="left",
        color=TEXT,
        fontsize=10.5,
        fontweight="bold",
        pad=4,
    )
    bivariate_axis.set_title(
        "Where the two maps agree",
        loc="left",
        color=TEXT,
        fontsize=11,
        fontweight="bold",
        pad=4,
    )

    add_map_legend(
        hle_legend_axis,
        HLE_BAND_COLOURS,
        HLE_BAND_LABELS,
        "Healthy life expectancy average, years",
    )

    q = rent_quintile_edges
    rent_legend_labels = (
        f"<{fmt(q[1], 1)}%",
        f"{fmt(q[1], 1)}–<{fmt(q[2], 1)}%",
        f"{fmt(q[2], 1)}–<{fmt(q[3], 1)}%",
        f"{fmt(q[3], 1)}–<{fmt(q[4], 1)}%",
        f"≥{fmt(q[4], 1)}%",
    )
    add_map_legend(
        rent_legend_axis,
        RENT_QUINTILE_COLOURS,
        rent_legend_labels,
        "Social-rent share of households, percent",
    )

    draw_bivariate_legend(bivariate_legend_axis)
    agreement_axis.set_facecolor(WHITE)
    agreement_axis.set_axis_off()
    agreement_axis.text(
        0.5,
        0.5,
        f"{diagonal_percentage:.1f}% of areas sit on the diagonal, where the two maps agree.",
        transform=agreement_axis.transAxes,
        ha="center",
        va="center",
        color=SECONDARY,
        fontsize=9,
    )

    figure.text(
        0.04,
        0.96,
        "Healthy life expectancy and social renting across 660 areas",
        ha="left",
        va="center",
        color=TEXT,
        fontsize=16,
        fontweight="bold",
    )
    figure.text(
        0.04,
        0.918,
        f"Areas with more social renting tend to have lower healthy life expectancy "
        f"(Spearman ρ = {spearman:.2f}, 660 areas). This is an area-level link, not a cause.",
        ha="left",
        va="center",
        color=SECONDARY,
        fontsize=9,
    )

    figure.savefig(FIGURE_PATH, format="webp", dpi=150, facecolor=WHITE)
    plt.close(figure)


def main():
    """Load, join, summarize, and render the requested comparison."""
    if not FIGURE_PATH.parent.is_dir() or not NUMBERS_PATH.parent.is_dir():
        raise FileNotFoundError("The requested assets/img and tools output folders must exist.")

    hle_by_code = read_hle_values()
    rent_by_code = read_tenure_values()
    features = read_boundaries()
    boundary_codes = {feature["properties"]["MSOA21CD"] for feature in features}

    if len(features) != 660:
        raise ValueError(f"Expected 660 MSOA boundaries, found {len(features)}.")
    if set(hle_by_code) != boundary_codes:
        raise ValueError("HLE source codes do not exactly match the 660 MSOA21 boundaries.")
    if not boundary_codes.issubset(rent_by_code):
        missing = sorted(boundary_codes.difference(rent_by_code))
        raise ValueError(f"TS054 is missing MSOA codes: {', '.join(missing[:10])}")

    codes = [feature["properties"]["MSOA21CD"] for feature in features]
    hle = np.asarray([hle_by_code[code] for code in codes], dtype=float)
    rent = np.asarray([rent_by_code[code] for code in codes], dtype=float)
    if not np.isfinite(hle).all() or not np.isfinite(rent).all():
        raise ValueError("HLE and tenure values must all be finite.")

    # Compute correlations and quantile boundaries from the exact matched 660 areas.
    spearman, pearson = correlation(rent, hle)
    rent_quintile_edges = quantile_edges(rent, (0, 0.2, 0.4, 0.6, 0.8, 1))
    hle_tertile_edges = quantile_edges(hle, (0, 1 / 3, 2 / 3, 1))
    rent_tertile_edges = quantile_edges(rent, (0, 1 / 3, 2 / 3, 1))

    hle_band_classes = np.searchsorted(HLE_BAND_EDGES, hle, side="right")
    rent_quintile_classes = classify(rent, rent_quintile_edges)
    hle_tertile_classes = classify(hle, hle_tertile_edges)
    rent_tertile_classes = classify(rent, rent_tertile_edges)

    # Count the 3 by 3 cells in the requested rent-low-to-high and HLE-high-to-low order.
    cell_counts = np.zeros((3, 3), dtype=int)
    for rent_class, hle_class in zip(rent_tertile_classes, hle_tertile_classes):
        cell_counts[int(rent_class), 2 - int(hle_class)] += 1
    diagonal_count = int(sum(cell_counts[index, index] for index in range(3)))
    diagonal_percentage = 100 * diagonal_count / len(codes)

    # Save the summary table and the WebP figure directly to the two requested output paths.
    write_numbers_csv(
        len(codes),
        spearman,
        pearson,
        rent_quintile_edges,
        hle_tertile_edges,
        rent_tertile_edges,
        cell_counts,
        diagonal_count,
    )
    make_figure(
        features,
        hle,
        rent,
        hle_band_classes,
        rent_quintile_classes,
        hle_tertile_classes,
        rent_tertile_classes,
        rent_quintile_edges,
        spearman,
        cell_counts,
        diagonal_percentage,
    )

    print(f"n={len(codes)}")
    print(f"Spearman={spearman:.6f}")
    print(f"Pearson={pearson:.6f}")
    print(f"Diagonal={diagonal_count}/{len(codes)} ({diagonal_percentage:.1f}%)")
    print("Cells, rows social rent low to high; columns HLE high to low:")
    for row in cell_counts:
        print(",".join(str(int(value)) for value in row))
    print(f"Figure: {FIGURE_PATH}")
    print(f"Numbers: {NUMBERS_PATH}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Could not make the tenure figure: {exc}", file=sys.stderr)
        raise
