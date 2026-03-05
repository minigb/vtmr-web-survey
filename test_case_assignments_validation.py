#!/usr/bin/env python3
"""Validation tests for generated VTMR test-case assignments.

Checks:
1) Every user has exactly 20 unique videos, each appearing exactly 2 times.
2) Non-random questions are uniformly distributed across combinations within each video.
3) Randomly selected combinations are counted and validated (exclude vidmuse).
"""

from __future__ import annotations

import json
import os
import unittest
from collections import Counter
from pathlib import Path


ASSIGNMENTS_PATH = Path(
    os.environ.get("ASSIGNMENTS_JSON", "data/test_case_assignments.json")
)
RANDOM_SOURCE = "random_non_vidmuse"
EXPECTED_USERS = 30
EXPECTED_QUESTIONS_PER_USER = 40
EXPECTED_VIDEOS_PER_USER = 20
EXPECTED_QUESTIONS_PER_VIDEO_PER_USER = 2
EXPECTED_RANDOM_QUESTIONS = 30


def load_assignments() -> dict:
    if not ASSIGNMENTS_PATH.exists():
        raise FileNotFoundError(
            f"Assignment file not found: {ASSIGNMENTS_PATH}. "
            "Run generate_test_cases.py first."
        )
    return json.loads(ASSIGNMENTS_PATH.read_text(encoding="utf-8"))


class TestCaseAssignmentsValidation(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = load_assignments()
        cls.users = cls.payload["users"]

    def test_1_user_has_20_videos_and_two_questions_per_video(self) -> None:
        self.assertEqual(len(self.users), EXPECTED_USERS, "Unexpected user count")
        for user_id, questions in self.users.items():
            self.assertEqual(
                len(questions),
                EXPECTED_QUESTIONS_PER_USER,
                f"{user_id}: unexpected question count",
            )
            by_video = Counter(q["video_id"] for q in questions)
            self.assertEqual(
                len(by_video),
                EXPECTED_VIDEOS_PER_USER,
                f"{user_id}: expected {EXPECTED_VIDEOS_PER_USER} unique videos, got {len(by_video)}",
            )
            for video_id, count in sorted(by_video.items()):
                self.assertEqual(
                    count,
                    EXPECTED_QUESTIONS_PER_VIDEO_PER_USER,
                    f"{user_id}: video {video_id} appears {count} times",
                )

    def test_2_non_random_cases_are_uniform(self) -> None:
        by_video_counts = {}
        for questions in self.users.values():
            for q in questions:
                if q.get("source") == RANDOM_SOURCE:
                    continue
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
            unique_counts = set(counts.values())
            self.assertEqual(
                len(unique_counts),
                1,
                f"{video_id}: non-random combination counts are not uniform: {sorted(unique_counts)}",
            )

    def test_3_random_case_count_and_exclusion(self) -> None:
        random_questions = [
            q
            for questions in self.users.values()
            for q in questions
            if q.get("source") == RANDOM_SOURCE
        ]
        self.assertEqual(
            len(random_questions),
            EXPECTED_RANDOM_QUESTIONS,
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
        self.assertGreater(len(random_case_counts), 0, "No random case counts found")
        print("\nRandom combination counts:", dict(sorted(random_case_counts.items())))


if __name__ == "__main__":
    unittest.main(verbosity=2)
