from __future__ import annotations

import json
import unittest
from pathlib import Path

from app.importers.telegram import flatten_text, load_telegram_export, normalize_chat_id


class TelegramImporterTests(unittest.TestCase):
    def test_flatten_text(self) -> None:
        self.assertEqual(flatten_text("plain"), "plain")
        self.assertEqual(
            flatten_text(["hello ", {"type": "link", "text": "https://example.com"}]),
            "hello https://example.com",
        )

    def test_normalize_supergroup_id(self) -> None:
        self.assertEqual(normalize_chat_id(-1003787023644), "3787023644")

    def test_load_export(self) -> None:
        payload = {
            "id": -1003787023644,
            "name": "WB test chat",
            "type": "public_supergroup",
            "messages": [
                {"id": 1, "type": "service", "date": "2026-01-01T00:00:00"},
                {
                    "id": 2,
                    "type": "message",
                    "date": "2026-01-01T00:01:00",
                    "from": "Seller",
                    "from_id": "user1",
                    "text": ["Как считать ", {"type": "bold", "text": "маржу"}],
                },
            ],
        }

        path = Path.cwd() / "tests" / "_tmp_result.json"
        try:
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            result = load_telegram_export(path)
        finally:
            if path.exists():
                path.unlink()

        self.assertEqual(result.chat.chat_id, "3787023644")
        self.assertEqual(result.chat.total_messages, 1)
        self.assertEqual(result.messages[0].text, "Как считать маржу")


if __name__ == "__main__":
    unittest.main()
