#!/usr/bin/env python3
import argparse
import json
import itertools
from collections import defaultdict
from pathlib import Path

OPTIONS = ("vidmuse", "vtmr", "firefly", "reference")


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

            pair_key = tuple(sorted((option_a, option_b)))
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


def print_report(title, stats):
    print(f"\n=== {title} ===")
    for a, b in itertools.combinations(OPTIONS, 2):
        s = stats[(a, b)]
        total = s["total"]
        ties = s["ties"]
        wa = s["wins"][a]
        wb = s["wins"][b]

        a_win_rate = pct(wa, total)
        b_win_rate = pct(wb, total)
        a_win_tie_rate = pct(wa + ties, total)
        b_win_tie_rate = pct(wb + ties, total)

        print(f"{a:9s} vs {b:9s} | n={total:4d} tie={ties:4d}")
        print(f"  {a:9s}: win_rate={a_win_rate:6.2f}%  win+tie_rate={a_win_tie_rate:6.2f}%")
        print(f"  {b:9s}: win_rate={b_win_rate:6.2f}%  win+tie_rate={b_win_tie_rate:6.2f}%")


def main():
    parser = argparse.ArgumentParser(
        description="Compute pairwise win rate and win+tie rate across vidmuse/vtmr/firefly/reference."
    )
    parser.add_argument(
        "--input",
        default="data/results.json",
        help="Path to results JSON (default: data/results.json)",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    with input_path.open("r", encoding="utf-8") as f:
        results_data = json.load(f)

    metrics = find_metrics(results_data)
    if not metrics:
        print("No metric keys found in results. Nothing to analyze.")
        return

    per_metric, overall = compute_stats(results_data, metrics)

    print(f"Loaded: {input_path}")
    print(f"Metrics detected: {', '.join(metrics)}")
    print_report("OVERALL (all metrics combined)", overall)
    for metric in metrics:
        print_report(f"METRIC: {metric}", per_metric[metric])


if __name__ == "__main__":
    main()
