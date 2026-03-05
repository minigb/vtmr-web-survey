#!/usr/bin/env python3
"""Generate fixed test-case assignments for VTMR survey users.

Default behavior:
- 30 users
- 40 questions per user
- each user sees all 20 videos, 2 questions per video
- 1170 non-random ("balanced") + 30 random_non_vidmuse questions
- non-random combinations are uniform *within each video*
"""

from __future__ import annotations

import argparse
import csv
import heapq
import itertools
import json
import random
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

VIDEO_EXTENSIONS = {".mp4", ".webm", ".ogg"}
KNOWN_OPTIONS = ("reference", "vtmr", "firefly", "vidmuse")
OPTION_ORDER = {name: idx for idx, name in enumerate(KNOWN_OPTIONS)}


@dataclass(frozen=True)
class Candidate:
    option: str
    file_rel: str
    video_obj_id: str


@dataclass(frozen=True)
class Case:
    video_id: str
    a: Candidate
    b: Candidate

    @property
    def case_id(self) -> str:
        return f"{self.video_id}::{self.a.option}_vs_{self.b.option}"


def detect_option(filename: str) -> str:
    text = filename.lower()
    for option in KNOWN_OPTIONS:
        if option in text:
            return option
    return Path(filename).stem.lower()


def sort_key_for_candidate(candidate: Candidate) -> tuple[int, str]:
    return (OPTION_ORDER.get(candidate.option, len(OPTION_ORDER)), candidate.file_rel)


def discover_cases(videos_dir: Path) -> tuple[list[Case], dict[str, list[Candidate]]]:
    if not videos_dir.exists() or not videos_dir.is_dir():
        raise ValueError(f"Videos directory does not exist: {videos_dir}")

    per_video_candidates: dict[str, list[Candidate]] = {}
    all_cases: list[Case] = []

    for video_dir in sorted([p for p in videos_dir.iterdir() if p.is_dir()]):
        candidates: list[Candidate] = []
        for file_path in sorted(video_dir.iterdir()):
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in VIDEO_EXTENSIONS:
                continue

            option = detect_option(file_path.name)
            file_rel = str(file_path.relative_to(videos_dir.parent))
            video_obj_id = f"{video_dir.name}_{file_path.stem}"
            candidates.append(Candidate(option=option, file_rel=file_rel, video_obj_id=video_obj_id))

        candidates.sort(key=sort_key_for_candidate)
        if len(candidates) < 2:
            continue

        per_video_candidates[video_dir.name] = candidates
        for left, right in itertools.combinations(candidates, 2):
            all_cases.append(Case(video_id=video_dir.name, a=left, b=right))

    return all_cases, per_video_candidates


def cases_by_video(cases: list[Case]) -> dict[str, list[Case]]:
    out: dict[str, list[Case]] = defaultdict(list)
    for case in cases:
        out[case.video_id].append(case)
    for video_id in list(out.keys()):
        out[video_id] = sorted(out[video_id], key=lambda c: c.case_id)
    return dict(sorted(out.items()))


def make_question(case: Case, source: str, rng: random.Random) -> dict:
    pair = [
        {"id": case.a.video_obj_id, "file": case.a.file_rel, "option": case.a.option},
        {"id": case.b.video_obj_id, "file": case.b.file_rel, "option": case.b.option},
    ]
    if rng.random() < 0.5:
        pair[0], pair[1] = pair[1], pair[0]

    return {
        "video_id": case.video_id,
        "case_id": case.case_id,
        "source": source,
        "pair": pair,
    }


def generate_assignments(
    cases: list[Case],
    users: int,
    questions_per_user: int,
    balanced_questions: int,
    random_questions: int,
    random_exclude_option: str,
    seed: int,
) -> dict:
    total_questions = users * questions_per_user
    requested_total = balanced_questions + random_questions
    if requested_total != total_questions:
        raise ValueError(
            "Total mismatch: users * questions_per_user must equal "
            "balanced_questions + random_questions "
            f"({total_questions} != {requested_total})"
        )

    if not cases:
        raise ValueError("No valid cases discovered from the videos directory.")

    rng = random.Random(seed)
    user_ids = [f"user_{i:02d}" for i in range(1, users + 1)]
    by_video = cases_by_video(cases)
    num_videos = len(by_video)
    expected_questions_per_user = num_videos * 2
    if expected_questions_per_user != questions_per_user:
        raise ValueError(
            f"questions_per_user must be num_videos * 2 ({expected_questions_per_user}), "
            f"got {questions_per_user}"
        )

    slots_per_video = users * 2
    if balanced_questions != total_questions - random_questions:
        raise ValueError(
            f"balanced_questions must be total - random ({total_questions - random_questions}), "
            f"got {balanced_questions}"
        )

    video_ids = list(by_video.keys())
    random_chunks: dict[str, int] = {video_id: 0 for video_id in video_ids}
    eligible_video_ids = [
        video_id
        for video_id in video_ids
        if any(
            case.a.option != random_exclude_option and case.b.option != random_exclude_option
            for case in by_video[video_id]
        )
    ]
    if random_questions > 0 and not eligible_video_ids:
        raise ValueError(
            f"No eligible videos for random sampling when excluding '{random_exclude_option}'."
        )

    # Allocate random questions in chunks equal to number of cases in each video so that
    # (slots_per_video - random_chunks[video]) is divisible by case count.
    remaining_random = random_questions
    ordered_for_random = sorted(
        eligible_video_ids,
        key=lambda video_id: (len(by_video[video_id]), video_id),
    )
    while remaining_random > 0:
        progressed = False
        for video_id in ordered_for_random:
            chunk = len(by_video[video_id])
            if chunk > remaining_random:
                continue
            # Keep at least 1 non-random sample per case.
            if random_chunks[video_id] + chunk > (slots_per_video - chunk):
                continue
            random_chunks[video_id] += chunk
            remaining_random -= chunk
            progressed = True
            if remaining_random == 0:
                break
        if not progressed:
            raise ValueError(
                "Could not allocate random questions while preserving per-video uniform non-random counts. "
                f"remaining_random={remaining_random}"
            )

    assignments: dict[str, list[dict]] = {user_id: [] for user_id in user_ids}
    case_lookup = {case.case_id: case for case in cases}
    random_needed_per_case: Counter[str] = Counter()
    occurrences_per_case: defaultdict[str, list[dict]] = defaultdict(list)

    def _pair_case_tokens(case_counts: dict[str, int]) -> list[tuple[str, str]]:
        total = sum(case_counts.values())
        if total != slots_per_video:
            raise ValueError(f"Per-video token total must be {slots_per_video}, got {total}")
        if max(case_counts.values(), default=0) > slots_per_video // 2:
            raise ValueError(f"Case distribution too skewed for distinct pairing: {case_counts}")

        heap: list[tuple[int, float, str]] = []
        for case_id, count in case_counts.items():
            if count > 0:
                heapq.heappush(heap, (-count, rng.random(), case_id))

        pairs: list[tuple[str, str]] = []
        while heap:
            if len(heap) < 2:
                raise ValueError(f"Pairing failed; leftover token for case {heap[0][2]}")
            neg1, _, case1 = heapq.heappop(heap)
            neg2, _, case2 = heapq.heappop(heap)
            pairs.append((case1, case2))

            count1 = -neg1 - 1
            count2 = -neg2 - 1
            if count1 > 0:
                heapq.heappush(heap, (-count1, rng.random(), case1))
            if count2 > 0:
                heapq.heappush(heap, (-count2, rng.random(), case2))

        if len(pairs) != users:
            raise ValueError(f"Expected {users} pairs for a video, got {len(pairs)}")
        return pairs

    for video_id in video_ids:
        video_cases = by_video[video_id]
        case_count = len(video_cases)
        random_for_video = random_chunks[video_id]
        non_random_total = slots_per_video - random_for_video
        if non_random_total % case_count != 0:
            raise ValueError(
                f"Non-random total {non_random_total} for {video_id} not divisible by case count {case_count}"
            )
        non_random_per_case = non_random_total // case_count

        case_total_counts: dict[str, int] = {case.case_id: non_random_per_case for case in video_cases}

        eligible_case_ids = [
            case.case_id
            for case in video_cases
            if case.a.option != random_exclude_option and case.b.option != random_exclude_option
        ]
        if random_for_video > 0 and not eligible_case_ids:
            raise ValueError(f"No eligible random cases in video {video_id}")

        # Spread random assignments across eligible cases in shuffled round-robin.
        rr = eligible_case_ids[:]
        rng.shuffle(rr)
        for i in range(random_for_video):
            target_case = rr[i % len(rr)]
            case_total_counts[target_case] += 1
            random_needed_per_case[target_case] += 1

        case_pairs = _pair_case_tokens(case_total_counts)
        rng.shuffle(case_pairs)
        for user_id, (case1_id, case2_id) in zip(user_ids, case_pairs):
            for case_id in (case1_id, case2_id):
                q = make_question(case_lookup[case_id], "balanced", rng)
                occurrences_per_case[case_id].append(q)
                assignments[user_id].append(q)

    # Mark random questions per case (random draws come from eligible non-vidmuse case IDs only).
    for case_id, random_needed in random_needed_per_case.items():
        if random_needed <= 0:
            continue
        pool = occurrences_per_case[case_id]
        if random_needed > len(pool):
            raise ValueError(
                f"Random source assignment overflow for {case_id}: need {random_needed}, have {len(pool)}"
            )
        for q in rng.sample(pool, random_needed):
            q["source"] = "random_non_vidmuse"

    for user_id in user_ids:
        user_questions = assignments[user_id]
        if len(user_questions) != questions_per_user:
            raise ValueError(f"{user_id} has {len(user_questions)} questions, expected {questions_per_user}")
        rng.shuffle(user_questions)
        for i, q in enumerate(user_questions, start=1):
            q["question_no"] = i

    return {
        "seed": seed,
        "users": assignments,
    }


def build_summary(assignments: dict, cases: list[Case], per_video_candidates: dict[str, list[Candidate]]) -> dict:
    all_questions = [q for q_list in assignments["users"].values() for q in q_list]
    case_counter = Counter(q["case_id"] for q in all_questions)
    source_counter = Counter(q["source"] for q in all_questions)
    video_counter = Counter(q["video_id"] for q in all_questions)
    non_random_case_counter = Counter(q["case_id"] for q in all_questions if q["source"] == "balanced")

    case_lookup = {case.case_id: case for case in cases}
    random_non_vidmuse_valid = all(
        "vidmuse" not in {case_lookup[q["case_id"]].a.option, case_lookup[q["case_id"]].b.option}
        for q in all_questions
        if q["source"] == "random_non_vidmuse"
    )

    per_video_candidate_counts = {video_id: len(cands) for video_id, cands in sorted(per_video_candidates.items())}
    per_video_case_counts = defaultdict(int)
    for case in cases:
        per_video_case_counts[case.video_id] += 1

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "total_users": len(assignments["users"]),
        "questions_per_user": len(next(iter(assignments["users"].values()))) if assignments["users"] else 0,
        "total_questions": len(all_questions),
        "total_cases": len(cases),
        "source_counts": dict(sorted(source_counter.items())),
        "random_non_vidmuse_valid": random_non_vidmuse_valid,
        "per_video_candidate_counts": per_video_candidate_counts,
        "per_video_case_counts": dict(sorted(per_video_case_counts.items())),
        "per_video_question_counts": dict(sorted(video_counter.items())),
        "case_counts": dict(sorted(case_counter.items())),
        "non_random_case_counts": dict(sorted(non_random_case_counter.items())),
    }


def write_csv(assignments: dict, output_csv: Path) -> None:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    for user_id, questions in assignments["users"].items():
        for q in questions:
            pair = q["pair"]
            rows.append(
                {
                    "user_id": user_id,
                    "question_no": q["question_no"],
                    "video_id": q["video_id"],
                    "case_id": q["case_id"],
                    "source": q["source"],
                    "a_option": pair[0]["option"],
                    "a_id": pair[0]["id"],
                    "a_file": pair[0]["file"],
                    "b_option": pair[1]["option"],
                    "b_id": pair[1]["id"],
                    "b_file": pair[1]["file"],
                }
            )

    fieldnames = [
        "user_id",
        "question_no",
        "video_id",
        "case_id",
        "source",
        "a_option",
        "a_id",
        "a_file",
        "b_option",
        "b_id",
        "b_file",
    ]
    with output_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def generate_token(prefix: str, rng: random.Random, used: set[str], nbytes: int = 12) -> str:
    while True:
        token = f"{prefix}_{rng.getrandbits(nbytes * 8):0{nbytes * 2}x}"
        if token not in used:
            used.add(token)
            return token


def build_public_payload(
    payload: dict,
    cases: list[Case],
    seed: int,
) -> tuple[dict, dict]:
    """Create participant-safe payload + private mapping.

    Public payload intentionally excludes candidate labels and real file paths.
    """
    rng = random.Random(seed + 7919)
    used_tokens: set[str] = set()

    # Build anonymized video tokens for each concrete media file.
    file_to_video_token: dict[str, str] = {}
    video_token_to_private: dict[str, dict] = {}
    for case in cases:
        for cand in (case.a, case.b):
            if cand.file_rel in file_to_video_token:
                continue
            token = generate_token("v", rng, used_tokens)
            file_to_video_token[cand.file_rel] = token
            video_token_to_private[token] = {
                "file": cand.file_rel,
                "id": cand.video_obj_id,
                "option": cand.option,
            }

    # Build anonymized case tokens.
    case_id_to_token: dict[str, str] = {}
    case_token_to_private: dict[str, dict] = {}
    for case in cases:
        case_token = generate_token("c", rng, used_tokens)
        case_id_to_token[case.case_id] = case_token
        case_token_to_private[case_token] = {
            "case_id": case.case_id,
            "video_id": case.video_id,
            "a_option": case.a.option,
            "b_option": case.b.option,
            "a_file": case.a.file_rel,
            "b_file": case.b.file_rel,
        }

    public_users: dict[str, list[dict]] = {}
    for user_id, questions in payload["users"].items():
        out_questions: list[dict] = []
        for q in questions:
            out_questions.append(
                {
                    "question_no": q["question_no"],
                    "video_id": q["video_id"],
                    "case_token": case_id_to_token[q["case_id"]],
                    "pair": [
                        {"file": file_to_video_token[q["pair"][0]["file"]]},
                        {"file": file_to_video_token[q["pair"][1]["file"]]},
                    ],
                }
            )
        public_users[user_id] = out_questions

    internal_summary = payload["summary"]
    source_counts = internal_summary.get("source_counts", {})
    public_source_counts = {
        "balanced": int(source_counts.get("balanced", 0)),
        "random_extra": int(source_counts.get("random_non_vidmuse", 0)),
    }
    case_counts = internal_summary.get("case_counts", {})
    non_random_case_counts = internal_summary.get("non_random_case_counts", {})
    case_token_counts = {
        case_id_to_token[case_id]: count
        for case_id, count in case_counts.items()
        if case_id in case_id_to_token
    }
    non_random_case_token_counts = {
        case_id_to_token[case_id]: count
        for case_id, count in non_random_case_counts.items()
        if case_id in case_id_to_token
    }

    public_summary = {
        "generated_at_utc": internal_summary.get("generated_at_utc"),
        "total_users": internal_summary.get("total_users"),
        "questions_per_user": internal_summary.get("questions_per_user"),
        "total_questions": internal_summary.get("total_questions"),
        "total_cases": internal_summary.get("total_cases"),
        "source_counts": public_source_counts,
        "random_exclusion_valid": bool(internal_summary.get("random_non_vidmuse_valid", False)),
        "per_video_candidate_counts": internal_summary.get("per_video_candidate_counts", {}),
        "per_video_case_counts": internal_summary.get("per_video_case_counts", {}),
        "per_video_question_counts": internal_summary.get("per_video_question_counts", {}),
        "case_token_counts": dict(sorted(case_token_counts.items())),
        "non_random_case_token_counts": dict(sorted(non_random_case_token_counts.items())),
    }

    base_meta = payload["meta"]
    public_payload = {
        "meta": {
            "videos_dir": base_meta.get("videos_dir"),
            "seed": base_meta.get("seed"),
            "users": base_meta.get("users"),
            "questions_per_user": base_meta.get("questions_per_user"),
            "balanced_questions": base_meta.get("balanced_questions"),
            "random_questions": base_meta.get("random_questions"),
            "sanitized_for_participants": True,
            "notes": "No candidate labels or real file paths are included.",
        },
        "summary": public_summary,
        "users": public_users,
    }
    private_map = {
        "meta": {
            "generated_from_seed": seed,
            "warning": "Sensitive mapping. Do not expose to participants.",
        },
        "video_token_to_private": dict(sorted(video_token_to_private.items())),
        "case_token_to_private": dict(sorted(case_token_to_private.items())),
    }
    return public_payload, private_map


def write_public_csv(public_payload: dict, output_csv: Path) -> None:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    for user_id, questions in public_payload["users"].items():
        for q in questions:
            rows.append(
                {
                    "user_id": user_id,
                    "question_no": q["question_no"],
                    "video_id": q["video_id"],
                    "case_token": q["case_token"],
                    "a_file_token": q["pair"][0]["file"],
                    "b_file_token": q["pair"][1]["file"],
                }
            )
    with output_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "user_id",
                "question_no",
                "video_id",
                "case_token",
                "a_file_token",
                "b_file_token",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate VTMR survey test-case assignments.")
    parser.add_argument("--videos-dir", type=Path, default=Path("videos"))
    parser.add_argument("--users", type=int, default=30)
    parser.add_argument("--questions-per-user", type=int, default=40)
    parser.add_argument("--balanced-questions", type=int, default=1170)
    parser.add_argument("--random-questions", type=int, default=30)
    parser.add_argument("--random-exclude-option", type=str, default="vidmuse")
    parser.add_argument("--seed", type=int, default=20260305)
    parser.add_argument("--output-json", type=Path, default=Path("data/test_case_assignments.json"))
    parser.add_argument("--output-csv", type=Path, default=Path("data/test_case_assignments.csv"))
    parser.add_argument(
        "--output-public-json",
        type=Path,
        default=Path("data/test_case_assignments_public.json"),
    )
    parser.add_argument(
        "--output-public-csv",
        type=Path,
        default=Path("data/test_case_assignments_public.csv"),
    )
    parser.add_argument(
        "--output-private-map-json",
        type=Path,
        default=Path("data/test_case_assignments_private_map.json"),
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)

    cases, per_video_candidates = discover_cases(args.videos_dir)
    assignments = generate_assignments(
        cases=cases,
        users=args.users,
        questions_per_user=args.questions_per_user,
        balanced_questions=args.balanced_questions,
        random_questions=args.random_questions,
        random_exclude_option=args.random_exclude_option,
        seed=args.seed,
    )
    summary = build_summary(assignments, cases, per_video_candidates)

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "meta": {
            "videos_dir": str(args.videos_dir),
            "seed": args.seed,
            "users": args.users,
            "questions_per_user": args.questions_per_user,
            "balanced_questions": args.balanced_questions,
            "random_questions": args.random_questions,
            "random_exclude_option": args.random_exclude_option,
        },
        "summary": summary,
        "users": assignments["users"],
    }
    args.output_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    write_csv(assignments, args.output_csv)

    public_payload, private_map = build_public_payload(payload, cases, args.seed)
    args.output_public_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_private_map_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_public_json.write_text(json.dumps(public_payload, indent=2), encoding="utf-8")
    args.output_private_map_json.write_text(json.dumps(private_map, indent=2), encoding="utf-8")
    write_public_csv(public_payload, args.output_public_csv)

    print(f"Generated {summary['total_questions']} questions for {summary['total_users']} users.")
    print(f"Total cases: {summary['total_cases']}")
    print(f"Source counts: {summary['source_counts']}")
    print(f"Random non-vidmuse valid: {summary['random_non_vidmuse_valid']}")
    print(f"Internal JSON: {args.output_json}")
    print(f"Internal CSV:  {args.output_csv}")
    print(f"Public JSON:   {args.output_public_json}")
    print(f"Public CSV:    {args.output_public_csv}")
    print(f"Private map:   {args.output_private_map_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
