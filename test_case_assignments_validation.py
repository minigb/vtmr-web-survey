#!/usr/bin/env python3
"""Validation tests for generated VTMR test-case assignments.

Checks:
1) Every user has exactly 20 unique videos, each appearing exactly 2 times.
2) Total questions are uniformly distributed across combinations within each video.
3) Randomly selected combinations are counted and validated.

Supports both:
- internal format (`case_id`, `source`, `pair[*].option`)
- public/tokenized format (`case_token`, no option labels)
"""

from __future__ import annotations

import json
import os
import unittest
from collections import Counter
from pathlib import Path


ASSIGNMENTS_PATH = Path(
    os.environ.get("ASSIGNMENTS_JSON", "data/test_case_assignments_public.json")
)
PRIVATE_MAP_PATH = Path(
    os.environ.get("PRIVATE_MAP_JSON", "data/test_case_assignments_private_map.json")
)
RANDOM_SOURCE = "random_non_vidmuse"
DEFAULT_EXPECTED_USERS = 30
DEFAULT_EXPECTED_QUESTIONS_PER_USER = 40
DEFAULT_EXPECTED_QUESTIONS_PER_VIDEO_PER_USER = 2
DEFAULT_EXPECTED_RANDOM_QUESTIONS = 30
OPTION_ORDER = {"reference": 0, "vtmr": 1, "firefly": 2, "vidmuse": 3}


def load_assignments() -> dict:
    if not ASSIGNMENTS_PATH.exists():
        raise FileNotFoundError(
            f"Assignment file not found: {ASSIGNMENTS_PATH}. "
            "Run generate_test_cases.py first."
        )
    return json.loads(ASSIGNMENTS_PATH.read_text(encoding="utf-8"))


def load_private_case_map() -> dict[str, dict]:
    if not PRIVATE_MAP_PATH.exists():
        return {}
    payload = json.loads(PRIVATE_MAP_PATH.read_text(encoding="utf-8"))
    return payload.get("case_token_to_private", {})


class TestCaseAssignmentsValidation(unittest.TestCase):
    @staticmethod
    def _int_or_default(value: object, default: int) -> int:
        try:
            if value is None:
                return default
            return int(value)
        except (TypeError, ValueError):
            return default

    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = load_assignments()
        cls.meta = cls.payload.get("meta", {})
        cls.users = cls.payload["users"]
        cls.summary = cls.payload.get("summary", {})
        cls.private_case_map = load_private_case_map()
        cls.expected_users = cls._int_or_default(
            cls.meta.get("users"),
            DEFAULT_EXPECTED_USERS,
        )
        cls.expected_questions_per_user = cls._int_or_default(
            cls.meta.get("questions_per_user"),
            DEFAULT_EXPECTED_QUESTIONS_PER_USER,
        )
        cls.expected_random_questions = cls._int_or_default(
            cls.meta.get("random_questions"),
            DEFAULT_EXPECTED_RANDOM_QUESTIONS,
        )
        cls.expected_questions_per_video_per_user = DEFAULT_EXPECTED_QUESTIONS_PER_VIDEO_PER_USER
        cls.expected_videos_per_user = (
            cls.expected_questions_per_user // cls.expected_questions_per_video_per_user
        )
        first_user = next(iter(cls.users.values()), [])
        first_question = first_user[0] if first_user else {}
        cls.is_public_format = "case_token" in first_question and "case_id" not in first_question

    def _build_token_to_video_map(self) -> dict[str, str]:
        token_to_video = {}
        for questions in self.users.values():
            for q in questions:
                token = q.get("case_token")
                video_id = q.get("video_id")
                if not token:
                    continue
                if token in token_to_video:
                    self.assertEqual(
                        token_to_video[token],
                        video_id,
                        f"Case token {token} maps to multiple videos",
                    )
                else:
                    token_to_video[token] = video_id
        return token_to_video

    @classmethod
    def _random_distribution(cls) -> Counter[str]:
        if cls.is_public_format:
            total_case_counts = cls.summary.get("case_token_counts", {})
            non_random_case_counts = cls.summary.get("non_random_case_token_counts", {})
            out: Counter[str] = Counter()
            for token, total in total_case_counts.items():
                diff = int(total) - int(non_random_case_counts.get(token, 0))
                if diff > 0:
                    out[token] = diff
            return out
        return Counter(
            q["case_id"]
            for questions in cls.users.values()
            for q in questions
            if q.get("source") == RANDOM_SOURCE
        )

    @staticmethod
    def _pair_label(option_a: str, option_b: str) -> str:
        a, b = sorted(
            [str(option_a), str(option_b)],
            key=lambda name: (OPTION_ORDER.get(name, 999), name),
        )
        return f"{a} vs {b}"

    @staticmethod
    def _parse_case_id_options(case_id: str) -> tuple[str, str]:
        tail = case_id.split("::", 1)[-1]
        if "_vs_" not in tail:
            return "unknown", "unknown"
        a, b = tail.split("_vs_", 1)
        return a, b

    @staticmethod
    def _short_name(path_or_name: str | None) -> str:
        if not path_or_name:
            return "unknown"
        return Path(path_or_name).stem

    @classmethod
    def _random_pair_breakdown(cls) -> tuple[Counter[str], dict[str, list[tuple[str, str, int]]], str | None]:
        random_counts = cls._random_distribution()
        grouped = {}
        pair_counter: Counter[str] = Counter()

        if cls.is_public_format:
            if not cls.private_case_map:
                return Counter(), {}, (
                    f"private map not found at {PRIVATE_MAP_PATH}; "
                    "cannot show A vs B labels/candidate names in public mode"
                )
            for token, count in random_counts.items():
                info = cls.private_case_map.get(token, {})
                option_a = str(info.get("a_option", "unknown"))
                option_b = str(info.get("b_option", "unknown"))
                pair_label = cls._pair_label(option_a, option_b)
                pair_counter[pair_label] += count

                video_id = str(info.get("video_id", "unknown_video"))
                a_name = cls._short_name(str(info.get("a_file", "")))
                b_name = cls._short_name(str(info.get("b_file", "")))
                grouped.setdefault(pair_label, [])
                grouped[pair_label].append((video_id, f"{a_name} vs {b_name}", count))
            return pair_counter, grouped, None

        # Internal format: pull details directly from random questions.
        details_by_case: dict[str, tuple[str, str, str]] = {}
        for questions in cls.users.values():
            for q in questions:
                if q.get("source") != RANDOM_SOURCE:
                    continue
                case_id = q["case_id"]
                if case_id in details_by_case:
                    continue
                option_a, option_b = cls._parse_case_id_options(case_id)
                pair = q.get("pair", [{}, {}])
                option_to_name = {}
                for entry in pair:
                    opt = str(entry.get("option", ""))
                    option_to_name[opt] = cls._short_name(str(entry.get("file", "")))
                a_name = option_to_name.get(
                    option_a,
                    cls._short_name(str(pair[0].get("file", ""))) if len(pair) > 0 else "unknown",
                )
                b_name = option_to_name.get(
                    option_b,
                    cls._short_name(str(pair[1].get("file", ""))) if len(pair) > 1 else "unknown",
                )
                details_by_case[case_id] = (
                    str(q.get("video_id", "unknown_video")),
                    cls._pair_label(option_a, option_b),
                    f"{a_name} vs {b_name}",
                )

        for case_id, count in random_counts.items():
            video_id, pair_label, candidate_text = details_by_case.get(
                case_id,
                ("unknown_video", "unknown vs unknown", "unknown vs unknown"),
            )
            pair_counter[pair_label] += count
            grouped.setdefault(pair_label, [])
            grouped[pair_label].append((video_id, candidate_text, count))

        return pair_counter, grouped, None

    @classmethod
    def _check_1_status(cls) -> tuple[bool, str]:
        if len(cls.users) != cls.expected_users:
            return False, f"user_count={len(cls.users)}"
        for user_id, questions in cls.users.items():
            if len(questions) != cls.expected_questions_per_user:
                return False, f"{user_id} question_count={len(questions)}"
            by_video = Counter(q["video_id"] for q in questions)
            if len(by_video) != cls.expected_videos_per_user:
                return False, f"{user_id} unique_videos={len(by_video)}"
            for video_id, count in by_video.items():
                if count != cls.expected_questions_per_video_per_user:
                    return False, f"{user_id} {video_id} count={count}"
        return True, f"{len(cls.users)} users checked"

    @classmethod
    def _check_2_status(cls) -> tuple[bool, str]:
        if cls.is_public_format:
            total_case_counts = cls.summary.get("case_token_counts", {})
            if not total_case_counts:
                return False, "missing case_token_counts"
            token_to_video: dict[str, str] = {}
            for questions in cls.users.values():
                for q in questions:
                    token = q.get("case_token")
                    if token:
                        token_to_video[token] = q["video_id"]
            by_video_counts: dict[str, Counter[str]] = {}
            for token, count in total_case_counts.items():
                video_id = token_to_video.get(token)
                if not video_id:
                    return False, f"token_without_video={token}"
                by_video_counts.setdefault(video_id, Counter())
                by_video_counts[video_id][token] = int(count)
        else:
            by_video_counts: dict[str, Counter[str]] = {}
            for questions in cls.users.values():
                for q in questions:
                    video_id = q["video_id"]
                    by_video_counts.setdefault(video_id, Counter())
                    by_video_counts[video_id][q["case_id"]] += 1
        if not by_video_counts:
            return False, "no per-video counts"
        for video_id, counts in by_video_counts.items():
            values = list(counts.values())
            spread = max(values) - min(values) if values else 0
            if spread > 1:
                return False, f"{video_id} count_spread={spread}"
        return True, f"{len(by_video_counts)} videos checked"

    @classmethod
    def _check_3_status(cls) -> tuple[bool, str]:
        random_distribution = cls._random_distribution()
        random_count = sum(random_distribution.values())
        if cls.is_public_format:
            exclusion_ok = bool(cls.summary.get("random_exclusion_valid", False))
        else:
            exclusion_ok = True
            for questions in cls.users.values():
                for q in questions:
                    if q.get("source") != RANDOM_SOURCE:
                        continue
                    options = {q["pair"][0]["option"], q["pair"][1]["option"]}
                    if "vidmuse" in options:
                        exclusion_ok = False
                        break
                if not exclusion_ok:
                    break
        has_distribution = len(random_distribution) > 0 if cls.expected_random_questions > 0 else True
        ok = random_count == cls.expected_random_questions and exclusion_ok and has_distribution
        return ok, f"random_count={random_count}, exclusion_ok={exclusion_ok}"

    @classmethod
    def tearDownClass(cls) -> None:
        status_1, msg_1 = cls._check_1_status()
        status_2, msg_2 = cls._check_2_status()
        status_3, msg_3 = cls._check_3_status()
        random_distribution = cls._random_distribution()

        fmt = "public/tokenized" if cls.is_public_format else "internal"
        print(f"\nValidation report ({fmt}) for {ASSIGNMENTS_PATH}:")
        print(
            f"- [{'PASS' if status_1 else 'FAIL'}] "
            f"Per-user {cls.expected_videos_per_user} videos x {cls.expected_questions_per_video_per_user} questions "
            f"({msg_1})"
        )
        print(f"- [{'PASS' if status_2 else 'FAIL'}] Total combination near-uniformity within each video ({msg_2})")
        print(f"- [{'PASS' if status_3 else 'FAIL'}] Random sample count/exclusion ({msg_3})")

        label = "case_token" if cls.is_public_format else "case_id"
        print(f"\nRandom {cls.expected_random_questions}-sample distribution ({label}):")
        for case_name, count in sorted(random_distribution.items(), key=lambda item: (-item[1], item[0])):
            print(f"  {case_name}: {count}")
        if not random_distribution:
            print("  (none)")

        pair_counter, grouped, warning = cls._random_pair_breakdown()
        print("\nRandom A vs B breakdown:")
        if warning:
            print(f"  {warning}")
        elif not pair_counter:
            print("  (none)")
        else:
            for pair_label, total_count in sorted(pair_counter.items(), key=lambda item: (-item[1], item[0])):
                print(f"  {pair_label}: {total_count}")
                candidates = sorted(grouped.get(pair_label, []), key=lambda item: (-item[2], item[0], item[1]))
                for video_id, candidate_text, count in candidates:
                    print(f"    - {video_id}: {candidate_text} ({count})")

    def test_1_user_has_20_videos_and_two_questions_per_video(self) -> None:
        self.assertEqual(len(self.users), self.expected_users, "Unexpected user count")
        for user_id, questions in self.users.items():
            self.assertEqual(
                len(questions),
                self.expected_questions_per_user,
                f"{user_id}: unexpected question count",
            )
            by_video = Counter(q["video_id"] for q in questions)
            self.assertEqual(
                len(by_video),
                self.expected_videos_per_user,
                f"{user_id}: expected {self.expected_videos_per_user} unique videos, got {len(by_video)}",
            )
            for video_id, count in sorted(by_video.items()):
                self.assertEqual(
                    count,
                    self.expected_questions_per_video_per_user,
                    f"{user_id}: video {video_id} appears {count} times",
                )

    def test_2_total_cases_are_uniform(self) -> None:
        if self.is_public_format:
            total_case_counts = self.summary.get("case_token_counts", {})
            self.assertTrue(
                total_case_counts,
                "Public format missing summary.case_token_counts",
            )
            token_to_video = self._build_token_to_video_map()
            by_video_counts = {}
            for token, count in total_case_counts.items():
                video_id = token_to_video.get(token)
                self.assertIsNotNone(video_id, f"Token {token} not found in user assignments")
                if video_id not in by_video_counts:
                    by_video_counts[video_id] = Counter()
                by_video_counts[video_id][token] = count
        else:
            by_video_counts = {}
            for questions in self.users.values():
                for q in questions:
                    video_id = q["video_id"]
                    if video_id not in by_video_counts:
                        by_video_counts[video_id] = Counter()
                    by_video_counts[video_id][q["case_id"]] += 1

        self.assertTrue(by_video_counts, "No non-random questions found")

        for video_id, counts in sorted(by_video_counts.items()):
            self.assertGreater(
                len(counts),
                0,
                f"{video_id}: no non-random combinations found",
            )
            values = list(counts.values())
            spread = max(values) - min(values) if values else 0
            self.assertLessEqual(
                spread,
                1,
                f"{video_id}: total combination counts are not near-uniform (max-min={spread})",
            )

    def test_3_random_case_count_and_exclusion(self) -> None:
        if self.is_public_format:
            source_counts = self.summary.get("source_counts", {})
            random_count = int(source_counts.get("random_extra", source_counts.get(RANDOM_SOURCE, 0)))
            self.assertEqual(
                random_count,
                self.expected_random_questions,
                "Unexpected random question count in public summary",
            )

            total_case_counts = self.summary.get("case_token_counts", {})
            non_random_case_counts = self.summary.get("non_random_case_token_counts", {})
            self.assertTrue(total_case_counts, "Public format missing summary.case_token_counts")
            self.assertTrue(
                non_random_case_counts,
                "Public format missing summary.non_random_case_token_counts",
            )

            random_case_counts = Counter()
            for token, total in total_case_counts.items():
                base = int(non_random_case_counts.get(token, 0))
                diff = int(total) - base
                self.assertGreaterEqual(diff, 0, f"Negative random diff for token {token}")
                if diff > 0:
                    random_case_counts[token] = diff

            self.assertEqual(
                sum(random_case_counts.values()),
                self.expected_random_questions,
                "Random token-count sum does not match expected random question count",
            )
            self.assertTrue(
                bool(self.summary.get("random_exclusion_valid", False)),
                "Public summary says random exclusion is invalid",
            )
            if self.expected_random_questions > 0:
                self.assertGreater(len(random_case_counts), 0, "No random case counts found")
            return

        random_questions = [
            q
            for questions in self.users.values()
            for q in questions
            if q.get("source") == RANDOM_SOURCE
        ]
        self.assertEqual(
            len(random_questions),
            self.expected_random_questions,
            "Unexpected random question count",
        )

        random_case_counts = Counter(q["case_id"] for q in random_questions)
        for q in random_questions:
            options = {q["pair"][0]["option"], q["pair"][1]["option"]}
            self.assertNotIn(
                "vidmuse",
                options,
                f"Found vidmuse in random question case {q['case_id']}",
            )

        # This assert gives a compact "count which combination is randomly selected" report.
        if self.expected_random_questions > 0:
            self.assertGreater(len(random_case_counts), 0, "No random case counts found")


if __name__ == "__main__":
    unittest.main(verbosity=2)
