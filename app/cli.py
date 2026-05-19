from __future__ import annotations

import argparse
from pathlib import Path

from app.importers.telegram import load_telegram_export
from app.storage.sqlite import Database


DEFAULT_DB = Path("data/db/chatkb.sqlite")


def main() -> None:
    parser = argparse.ArgumentParser(description="Market Pain Miner CLI")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Path to SQLite database")

    subparsers = parser.add_subparsers(dest="command", required=True)

    import_parser = subparsers.add_parser("import", help="Import Telegram Desktop result.json")
    import_parser.add_argument("result_json", help="Path to Telegram result.json")

    stats_parser = subparsers.add_parser("stats", help="Show database stats")
    stats_parser.add_argument("--latest", type=int, default=0, help="Show latest N messages")

    args = parser.parse_args()

    if args.command == "import":
        run_import(Path(args.result_json), Path(args.db))
    elif args.command == "stats":
        run_stats(Path(args.db), latest=args.latest)


def run_import(result_json: Path, db_path: Path) -> None:
    imported = load_telegram_export(result_json)
    db = Database(db_path)
    try:
        changed = db.import_chat(imported.chat, imported.messages)
    finally:
        db.close()

    print(f"Imported chat: {imported.chat.name or imported.chat.chat_id}")
    print(f"Messages in export: {len(imported.messages)}")
    print(f"Rows inserted/updated: {changed}")
    print(f"Database: {db_path}")


def run_stats(db_path: Path, latest: int = 0) -> None:
    db = Database(db_path)
    try:
        stats = db.stats()
        print(f"Chats: {stats['chats']}")
        print(f"Messages: {stats['messages']}")
        print(f"Labels: {stats['labels']}")

        if latest:
            print("")
            print(f"Latest {latest} messages:")
            for row in db.latest_messages(latest):
                preview = str(row["preview"]).replace("\n", " ")
                print(f"- {row['date']} #{row['msg_id']} {row['author']}: {preview}")
    finally:
        db.close()


if __name__ == "__main__":
    main()

