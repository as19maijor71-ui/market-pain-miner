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

    def test_rejects_invalid_json(self) -> None:
        path = Path.cwd() / "tests" / "_tmp_invalid_result.json"
        try:
            path.write_text("{not json", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "not valid JSON") as error:
                load_telegram_export(path)
            self.assertNotIn(str(path), str(error.exception))
        finally:
            if path.exists():
                path.unlink()

    def test_missing_export_error_does_not_leak_path(self) -> None:
        path = Path.cwd() / "tests" / "_tmp_missing_private_result.json"

        with self.assertRaisesRegex(ValueError, "does not exist") as error:
            load_telegram_export(path)

        self.assertNotIn(str(path), str(error.exception))

    def test_rejects_non_list_messages(self) -> None:
        path = Path.cwd() / "tests" / "_tmp_invalid_result.json"
        payload = {
            "id": -1003787023644,
            "name": "WB test chat",
            "type": "public_supergroup",
            "messages": {"id": 1},
        }
        try:
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "'messages' must be a list"):
                load_telegram_export(path)
        finally:
            if path.exists():
                path.unlink()

    def test_rejects_invalid_message_items(self) -> None:
        path = Path.cwd() / "tests" / "_tmp_invalid_result.json"
        payload = {
            "id": -1003787023644,
            "name": "WB test chat",
            "type": "public_supergroup",
            "messages": ["not an object"],
        }
        try:
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must be an object"):
                load_telegram_export(path)
        finally:
            if path.exists():
                path.unlink()

    def test_rejects_content_message_without_id(self) -> None:
        path = Path.cwd() / "tests" / "_tmp_invalid_result.json"
        payload = {
            "id": -1003787023644,
            "name": "WB test chat",
            "type": "public_supergroup",
            "messages": [{"type": "message", "text": "Привет"}],
        }
        try:
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "missing 'id'"):
                load_telegram_export(path)
        finally:
            if path.exists():
                path.unlink()


if __name__ == "__main__":
    unittest.main()
