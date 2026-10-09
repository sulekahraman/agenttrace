import unittest
import pytest

pytest.importorskip("inspect_scout")

from inspect_ai.model import ChatMessageAssistant

from agenttrace.scout.annotations import (
    MessageAnnotation,
    build_annotation_prompt,
    normalize_annotation,
)


class AnnotationTests(unittest.TestCase):
    def setUp(self):
        self.message = ChatMessageAssistant(
            content="Qi, please review #3 and art_example.",
            metadata={
                "participant_id": "Engineer AAAA",
                "sequence": 5,
                "timestamp": "2026-10-07T12:00:00Z",
                "annotation_context": {
                    "roster": [
                        {"id": "Engineer AAAA", "runtime": "claude-code"},
                        {"id": "Qi BBBB", "runtime": "codex"},
                    ],
                    "cited_messages": [
                        {
                            "index": 3,
                            "participant_id": "Qi BBBB",
                            "timestamp": "2026-10-07T11:00:00Z",
                            "text": "Earlier result.",
                        }
                    ],
                    "previous_messages": [],
                    "hints": {
                        "cites": [3],
                        "addressed_to": ["Qi BBBB"],
                        "artifacts": ["art_example"],
                        "heartbeat": False,
                    },
                },
            },
        )

    def test_prompt_contains_bounded_context(self):
        prompt = build_annotation_prompt(self.message)
        self.assertIn("TARGET MESSAGE TO LABEL", prompt)
        self.assertIn("#5 Engineer AAAA", prompt)
        self.assertIn("#3 Qi BBBB", prompt)
        self.assertIn('"artifacts": ["art_example"]', prompt)
        self.assertIn("lower than\n5", prompt)

    def test_normalization_enforces_links_and_roster(self):
        annotation = MessageAnnotation(
            primary_type="delegation_request",
            secondary_types=["delegation_request", "question"],
            replies_to=[5, 3, -1, 3],
            addressed_to=["Qi BBBB", "Unknown CCCC", "Qi BBBB"],
            confidence=0.8,
            ambiguous=False,
            rationale="Requests review.",
            evidence=[],
        )
        normalized = normalize_annotation(annotation, 5, {"Engineer AAAA", "Qi BBBB"})
        self.assertEqual(normalized.secondary_types, ["question"])
        self.assertEqual(normalized.replies_to, [3])
        self.assertEqual(normalized.addressed_to, ["Qi BBBB"])


if __name__ == "__main__":
    unittest.main()
