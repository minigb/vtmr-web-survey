#!/usr/bin/env python3
import argparse
import csv
import itertools
import json
from collections import defaultdict
from pathlib import Path

OPTIONS = ("vidmuse", "vtmr", "firefly", "reference")
OPTION_INDEX = {name: idx for idx, name in enumerate(OPTIONS)}


def detect_option(video_obj):
    if isinstance(video_obj, dict):
        parts = [
            str(video_obj.get("id", "")),
            str(video_obj.get("file", "")),
            str(video_obj.get("description", "")),
        ]
        text = " ".join(parts).lower()
    else:
        text = str(video_obj).lower()

    for option in OPTIONS:
        if option in text:
            return option
    return None


def init_pair_stats():
    stats = {}
    for pair in itertools.combinations(OPTIONS, 2):
        stats[pair] = {
            "total": 0,
            "ties": 0,
            "wins": {pair[0]: 0, pair[1]: 0},
        }
    return stats


def update_pair_stat(stats, pair, winner_option=None, tie=False):
    stats[pair]["total"] += 1
    if tie:
        stats[pair]["ties"] += 1
    elif winner_option in stats[pair]["wins"]:
        stats[pair]["wins"][winner_option] += 1


def get_outcome(vote, metric, option_a, option_b):
    result = vote.get("results", {}).get(metric)
    if isinstance(result, dict):
        if result.get("tie"):
            return "tie", None

        winner = detect_option(result.get("winner"))
        loser = detect_option(result.get("loser"))
        if winner in (option_a, option_b) and loser in (option_a, option_b) and winner != loser:
            return "win", winner

    choice = vote.get("choices", {}).get(metric)
    if choice == "TIE":
        return "tie", None
    if choice == "A":
        return "win", option_a
    if choice == "B":
        return "win", option_b

    return None, None


def find_metrics(results_data):
    metrics = set()
    for votes in results_data.values():
        if not isinstance(votes, list):
            continue
        for vote in votes:
            if not isinstance(vote, dict):
                continue
            metrics.update(vote.get("results", {}).keys())
            metrics.update(vote.get("choices", {}).keys())
    return sorted(metrics)


def compute_stats(results_data, metrics):
    per_metric = defaultdict(init_pair_stats)
    overall = init_pair_stats()

    for votes in results_data.values():
        if not isinstance(votes, list):
            continue

        for vote in votes:
            if not isinstance(vote, dict):
                continue

            pair = vote.get("pair", [])
            if not isinstance(pair, list) or len(pair) != 2:
                continue

            option_a = detect_option(pair[0])
            option_b = detect_option(pair[1])
            if not option_a or not option_b or option_a == option_b:
                continue

            pair_key = normalize_pair(option_a, option_b)
            if pair_key not in overall:
                continue

            for metric in metrics:
                outcome_type, winner = get_outcome(vote, metric, option_a, option_b)
                if outcome_type is None:
                    continue

                if outcome_type == "tie":
                    update_pair_stat(per_metric[metric], pair_key, tie=True)
                    update_pair_stat(overall, pair_key, tie=True)
                else:
                    update_pair_stat(per_metric[metric], pair_key, winner_option=winner, tie=False)
                    update_pair_stat(overall, pair_key, winner_option=winner, tie=False)

    return per_metric, overall


def pct(num, den):
    return 0.0 if den == 0 else (num / den) * 100.0


def normalize_pair(a, b):
    if OPTION_INDEX[a] <= OPTION_INDEX[b]:
        return (a, b)
    return (b, a)


def pair_values(stats, a, b):
    key = normalize_pair(a, b)
    s = stats[key]
    if a == key[0]:
        wins_a = s["wins"][key[0]]
        wins_b = s["wins"][key[1]]
    else:
        wins_a = s["wins"][key[1]]
        wins_b = s["wins"][key[0]]
    return s["total"], s["ties"], wins_a, wins_b


def report_lines(title, stats):
    lines = [f"\n=== {title} ==="]
    for a, b in itertools.combinations(OPTIONS, 2):
        total, ties, wa, wb = pair_values(stats, a, b)
        a_win_rate = pct(wa, total)
        b_win_rate = pct(wb, total)
        a_win_tie_rate = pct(wa + ties, total)
        b_win_tie_rate = pct(wb + ties, total)

        lines.append(f"{a:9s} vs {b:9s} | n={total:4d} tie={ties:4d}")
        lines.append(f"  {a:9s}: win_rate={a_win_rate:6.2f}%  win+tie_rate={a_win_tie_rate:6.2f}%")
        lines.append(f"  {b:9s}: win_rate={b_win_rate:6.2f}%  win+tie_rate={b_win_tie_rate:6.2f}%")
    return lines


def save_csv(output_path, per_metric, overall):
    fieldnames = [
        "metric",
        "option",
        "opponent",
        "total",
        "wins",
        "losses",
        "ties",
        "win_rate",
        "win_plus_tie_rate",
    ]
    rows = []

    for metric_name, stats in [("overall", overall), *sorted(per_metric.items())]:
        for a, b in itertools.combinations(OPTIONS, 2):
            total, ties, wa, wb = pair_values(stats, a, b)
            rows.append({
                "metric": metric_name,
                "option": a,
                "opponent": b,
                "total": total,
                "wins": wa,
                "losses": max(0, total - wa - ties),
                "ties": ties,
                "win_rate": f"{pct(wa, total):.4f}",
                "win_plus_tie_rate": f"{pct(wa + ties, total):.4f}",
            })
            rows.append({
                "metric": metric_name,
                "option": b,
                "opponent": a,
                "total": total,
                "wins": wb,
                "losses": max(0, total - wb - ties),
                "ties": ties,
                "win_rate": f"{pct(wb, total):.4f}",
                "win_plus_tie_rate": f"{pct(wb + ties, total):.4f}",
            })

    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def serialize_stats(stats):
    out = {}
    for pair in itertools.combinations(OPTIONS, 2):
        a, b = pair
        total, ties, wa, wb = pair_values(stats, a, b)
        out[f"{a}_vs_{b}"] = {
            "total": total,
            "ties": ties,
            a: {
                "wins": wa,
                "win_rate": pct(wa, total),
                "win_plus_tie_rate": pct(wa + ties, total),
            },
            b: {
                "wins": wb,
                "win_rate": pct(wb, total),
                "win_plus_tie_rate": pct(wb + ties, total),
            },
        }
    return out


def value_color(v):
    if v is None:
        return "#e6e6e6"
    t = max(0.0, min(1.0, v / 100.0))
    r = int(244 + (33 - 244) * t)
    g = int(244 + (113 - 244) * t)
    b = int(244 + (181 - 244) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


def save_heatmap_svg(output_path, stats, title, include_tie=False):
    cell = 120
    left = 150
    top = 90
    width = left + cell * len(OPTIONS) + 30
    height = top + cell * len(OPTIONS) + 40

    rate_name = "win+tie rate" if include_tie else "win rate"
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{left}" y="36" font-family="Arial" font-size="20" font-weight="bold">{title}</text>',
        f'<text x="{left}" y="62" font-family="Arial" font-size="14">{rate_name}</text>',
    ]

    for i, opt in enumerate(OPTIONS):
        x = left + i * cell + cell / 2
        y = top - 16
        lines.append(
            f'<text x="{x}" y="{y}" font-family="Arial" font-size="14" text-anchor="middle">{opt}</text>'
        )
        y2 = top + i * cell + cell / 2 + 5
        lines.append(
            f'<text x="{left - 14}" y="{y2}" font-family="Arial" font-size="14" text-anchor="end">{opt}</text>'
        )

    for row, a in enumerate(OPTIONS):
        for col, b in enumerate(OPTIONS):
            x = left + col * cell
            y = top + row * cell
            value = None

            if a != b:
                total, ties, wa, _ = pair_values(stats, a, b)
                if total > 0:
                    value = pct(wa + ties, total) if include_tie else pct(wa, total)

            fill = value_color(value)
            label = "NA" if value is None else f"{value:.1f}%"
            lines.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" fill="{fill}" stroke="#b0b0b0"/>')
            lines.append(
                f'<text x="{x + cell / 2}" y="{y + cell / 2 + 5}" font-family="Arial" font-size="16" '
                f'text-anchor="middle">{label}</text>'
            )

    lines.append("</svg>")
    output_path.write_text("\n".join(lines), encoding="utf-8")


def save_counts_svg(output_path, stats, title):
    pairs = list(itertools.combinations(OPTIONS, 2))
    max_total = max((stats[p]["total"] for p in pairs), default=0)
    max_total = max(1, max_total)

    width = 980
    height = 420
    margin_left = 80
    margin_bottom = 70
    chart_top = 70
    chart_height = height - chart_top - margin_bottom
    bar_w = 100
    gap = 45

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{margin_left}" y="32" font-family="Arial" font-size="20" font-weight="bold">{title}</text>',
        '<text x="80" y="54" font-family="Arial" font-size="14">gray: total comparisons, blue: ties</text>',
    ]

    x_axis_y = chart_top + chart_height
    lines.append(f'<line x1="{margin_left}" y1="{x_axis_y}" x2="{width - 30}" y2="{x_axis_y}" stroke="#333"/>')
    lines.append(f'<line x1="{margin_left}" y1="{chart_top}" x2="{margin_left}" y2="{x_axis_y}" stroke="#333"/>')

    for i, pair in enumerate(pairs):
        total = stats[pair]["total"]
        ties = stats[pair]["ties"]

        x = margin_left + 25 + i * (bar_w + gap)
        total_h = int((total / max_total) * chart_height)
        ties_h = int((ties / max_total) * chart_height)
        y_total = x_axis_y - total_h
        y_ties = x_axis_y - ties_h

        lines.append(f'<rect x="{x}" y="{y_total}" width="{bar_w}" height="{total_h}" fill="#d9d9d9" stroke="#9a9a9a"/>')
        lines.append(f'<rect x="{x}" y="{y_ties}" width="{bar_w}" height="{ties_h}" fill="#3182bd"/>')
        lines.append(
            f'<text x="{x + bar_w / 2}" y="{y_total - 8}" font-family="Arial" font-size="12" text-anchor="middle">{total}</text>'
        )
        lines.append(
            f'<text x="{x + bar_w / 2}" y="{x_axis_y + 20}" font-family="Arial" font-size="12" text-anchor="middle">{pair[0]} vs {pair[1]}</text>'
        )

    lines.append("</svg>")
    output_path.write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(
        description="Compute pairwise win rate and win+tie rate across vidmuse/vtmr/firefly/reference."
    )
    parser.add_argument(
        "--input",
        default="data/results.json",
        help="Path to results JSON (default: data/results.json)",
    )
    parser.add_argument(
        "--output-dir",
        default="data/pairwise_option_stats",
        help="Directory to save report files and graphs.",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with input_path.open("r", encoding="utf-8") as f:
        results_data = json.load(f)

    metrics = find_metrics(results_data)
    if not metrics:
        print("No metric keys found in results. Nothing to analyze.")
        return

    per_metric, overall = compute_stats(results_data, metrics)

    report = [f"Loaded: {input_path}", f"Metrics detected: {', '.join(metrics)}"]
    report.extend(report_lines("OVERALL (all metrics combined)", overall))
    for metric in metrics:
        report.extend(report_lines(f"METRIC: {metric}", per_metric[metric]))

    print("\n".join(report))

    # Save text, csv, json
    (output_dir / "pairwise_report.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
    save_csv(output_dir / "pairwise_rates.csv", per_metric, overall)

    payload = {
        "input_file": str(input_path),
        "metrics": metrics,
        "overall": serialize_stats(overall),
        "per_metric": {metric: serialize_stats(per_metric[metric]) for metric in metrics},
    }
    (output_dir / "pairwise_rates.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # Save graphs (SVG)
    save_heatmap_svg(output_dir / "overall_win_rate_heatmap.svg", overall, "Overall Pairwise Matrix", include_tie=False)
    save_heatmap_svg(
        output_dir / "overall_win_plus_tie_rate_heatmap.svg",
        overall,
        "Overall Pairwise Matrix",
        include_tie=True,
    )
    save_counts_svg(output_dir / "overall_pair_counts.svg", overall, "Overall Pair Counts")

    for metric in metrics:
        save_heatmap_svg(
            output_dir / f"{metric}_win_rate_heatmap.svg",
            per_metric[metric],
            f"Metric: {metric}",
            include_tie=False,
        )
        save_heatmap_svg(
            output_dir / f"{metric}_win_plus_tie_rate_heatmap.svg",
            per_metric[metric],
            f"Metric: {metric}",
            include_tie=True,
        )
        save_counts_svg(output_dir / f"{metric}_pair_counts.svg", per_metric[metric], f"Metric: {metric}")

    print(f"\nSaved report files to: {output_dir}")


if __name__ == "__main__":
    main()
