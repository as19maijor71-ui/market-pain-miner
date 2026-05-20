from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Iterable

from app.core.models import (
    ChatRecord,
    ClusterSourceMessage,
    LabelRecord,
    MessageRecord,
    SolutionSourceMessage,
)
from app.normalization import normalize_message_text


class Database:
    RUN_TABLE_SQL = """
            CREATE TABLE IF NOT EXISTS classifier_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL UNIQUE,
                source TEXT NOT NULL,
                classifier_name TEXT NOT NULL,
                classifier_version TEXT NOT NULL,
                started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                completed_at TEXT,
                message_count INTEGER NOT NULL DEFAULT 0,
                label_count INTEGER NOT NULL DEFAULT 0,
                UNIQUE (
                    run_id,
                    source,
                    classifier_name,
                    classifier_version
                )
            );
    """

    LABEL_TABLE_SQL = """
            CREATE TABLE IF NOT EXISTS message_labels (
                chat_id TEXT NOT NULL,
                msg_id INTEGER NOT NULL,
                category TEXT NOT NULL,
                topics TEXT NOT NULL DEFAULT '',
                confidence REAL NOT NULL DEFAULT 0,
                source TEXT NOT NULL DEFAULT 'rules',
                classifier_name TEXT NOT NULL DEFAULT 'rules',
                classifier_version TEXT NOT NULL DEFAULT 'legacy',
                run_id TEXT NOT NULL DEFAULT 'legacy',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (
                    chat_id,
                    msg_id,
                    source,
                    classifier_name,
                    classifier_version,
                    run_id
                ),
                FOREIGN KEY (chat_id, msg_id) REFERENCES messages(chat_id, msg_id),
                FOREIGN KEY (
                    run_id,
                    source,
                    classifier_name,
                    classifier_version
                ) REFERENCES classifier_runs (
                    run_id,
                    source,
                    classifier_name,
                    classifier_version
                )
            );
    """

    EFFECTIVE_LABELS_CTE = """
            WITH latest_classifier_run AS (
                SELECT source, classifier_name, classifier_version, run_id
                FROM classifier_runs AS r
                WHERE source <> 'manual'
                  AND EXISTS (
                      SELECT 1
                      FROM message_labels AS l
                      WHERE l.run_id = r.run_id
                  )
                ORDER BY id DESC
                LIMIT 1
            ),
            base_labels AS (
                SELECT
                    l.chat_id,
                    l.msg_id,
                    l.category,
                    l.topics,
                    l.confidence,
                    l.source,
                    l.classifier_name,
                    l.classifier_version,
                    l.run_id,
                    l.updated_at
                FROM message_labels AS l
                JOIN latest_classifier_run AS r
                  ON r.source = l.source
                 AND r.classifier_name = l.classifier_name
                 AND r.classifier_version = l.classifier_version
                 AND r.run_id = l.run_id
            ),
            manual_ranked AS (
                SELECT
                    l.chat_id,
                    l.msg_id,
                    l.category,
                    l.topics,
                    l.confidence,
                    l.source,
                    l.classifier_name,
                    l.classifier_version,
                    l.run_id,
                    l.updated_at,
                    ROW_NUMBER() OVER (
                        PARTITION BY l.chat_id, l.msg_id
                        ORDER BY r.id DESC,
                                 l.classifier_version DESC,
                                 l.run_id DESC
                    ) AS rank
                FROM message_labels AS l
                JOIN classifier_runs AS r
                  ON r.run_id = l.run_id
                WHERE l.source = 'manual'
            ),
            manual_labels AS (
                SELECT
                    chat_id,
                    msg_id,
                    category,
                    topics,
                    confidence,
                    source,
                    classifier_name,
                    classifier_version,
                    run_id,
                    updated_at
                FROM manual_ranked
                WHERE rank = 1
            ),
            effective_labels AS (
                SELECT *
                FROM base_labels AS b
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM manual_labels AS ml
                    WHERE ml.chat_id = b.chat_id
                      AND ml.msg_id = b.msg_id
                )
                UNION ALL
                SELECT *
                FROM manual_labels
            )
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA busy_timeout = 30000")
        self.conn.execute("PRAGMA foreign_keys = ON")
        try:
            self._initialize_with_retries()
        except Exception:
            self.conn.close()
            raise

    def close(self) -> None:
        self.conn.close()

    def _initialize_with_retries(self) -> None:
        for attempt in range(6):
            try:
                self.initialize()
                return
            except sqlite3.OperationalError as exc:
                if "database is locked" not in str(exc).lower() or attempt == 5:
                    raise
                self.conn.rollback()
                time.sleep(0.05 * (2**attempt))

    def initialize(self) -> None:
        self.conn.executescript(
            f"""
            PRAGMA journal_mode = WAL;

            CREATE TABLE IF NOT EXISTS chats (
                chat_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                total_messages INTEGER NOT NULL DEFAULT 0,
                imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS messages (
                chat_id TEXT NOT NULL,
                msg_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                author TEXT NOT NULL,
                from_id TEXT NOT NULL,
                topic_id TEXT,
                reply_to INTEGER,
                forwarded_from TEXT NOT NULL,
                text TEXT NOT NULL,
                normalized_text TEXT NOT NULL DEFAULT '',
                has_photo INTEGER NOT NULL,
                has_file INTEGER NOT NULL,
                media_type TEXT NOT NULL,
                raw_json TEXT NOT NULL,
                imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (chat_id, msg_id),
                FOREIGN KEY (chat_id) REFERENCES chats(chat_id)
            );

            {self.RUN_TABLE_SQL}

            {self.LABEL_TABLE_SQL}
            """
        )
        self._ensure_messages_schema()
        self._ensure_message_label_schema()
        self.conn.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_messages_date ON messages(date);
            CREATE INDEX IF NOT EXISTS idx_messages_author ON messages(author);
            CREATE INDEX IF NOT EXISTS idx_messages_normalized_text
                ON messages(normalized_text);
            CREATE INDEX IF NOT EXISTS idx_labels_category ON message_labels(category);
            CREATE INDEX IF NOT EXISTS idx_labels_classifier
                ON message_labels(source, classifier_name, classifier_version, run_id);
            CREATE INDEX IF NOT EXISTS idx_classifier_runs_lookup
                ON classifier_runs(source, classifier_name, classifier_version, id);
            """
        )
        self.conn.commit()

    def _ensure_messages_schema(self) -> None:
        table_info = list(self.conn.execute("PRAGMA table_info(messages)"))
        existing_columns = {row["name"] for row in table_info}
        if "normalized_text" not in existing_columns:
            try:
                self.conn.execute(
                    "ALTER TABLE messages "
                    "ADD COLUMN normalized_text TEXT NOT NULL DEFAULT ''"
                )
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise
        rows = list(
            self.conn.execute(
                """
                SELECT chat_id, msg_id, text
                FROM messages
                WHERE normalized_text = ''
                  AND text <> ''
                """
            )
        )
        self.conn.executemany(
            """
            UPDATE messages
            SET normalized_text = ?
            WHERE chat_id = ? AND msg_id = ?
            """,
            [
                (
                    normalize_message_text(str(row["text"])),
                    str(row["chat_id"]),
                    int(row["msg_id"]),
                )
                for row in rows
            ],
        )

    def _ensure_message_label_schema(self) -> None:
        table_info = list(self.conn.execute("PRAGMA table_info(message_labels)"))
        existing_columns = {row["name"] for row in table_info}
        pk_columns = [
            row["name"]
            for row in sorted(table_info, key=lambda item: int(item["pk"]))
            if row["pk"]
        ]
        expected_columns = {
            "chat_id",
            "msg_id",
            "category",
            "topics",
            "confidence",
            "source",
            "classifier_name",
            "classifier_version",
            "run_id",
            "created_at",
            "updated_at",
        }
        expected_pk = [
            "chat_id",
            "msg_id",
            "source",
            "classifier_name",
            "classifier_version",
            "run_id",
        ]
        if expected_columns.issubset(existing_columns) and pk_columns == expected_pk:
            self._ensure_runs_for_existing_labels()
            return

        self.conn.execute("ALTER TABLE message_labels RENAME TO message_labels_legacy")
        self.conn.executescript(self.LABEL_TABLE_SQL)

        def column_or_default(column: str, default: str) -> str:
            if column in existing_columns:
                return column
            return default

        source_expr = column_or_default("source", "'rules'")
        if "classifier_name" in existing_columns:
            classifier_name_expr = "classifier_name"
        else:
            classifier_name_expr = (
                "CASE "
                f"WHEN {source_expr} = 'manual' THEN 'manual' "
                f"WHEN {source_expr} = 'rules' THEN 'rules' "
                f"ELSE {source_expr} "
                "END"
            )

        run_sql = f"""
            INSERT OR IGNORE INTO classifier_runs (
                run_id,
                source,
                classifier_name,
                classifier_version,
                label_count
            )
            SELECT
                run_id,
                source,
                classifier_name,
                classifier_version,
                COUNT(*) AS label_count
            FROM (
                SELECT
                    {column_or_default("run_id", "'legacy'")} AS run_id,
                    {source_expr} AS source,
                    {classifier_name_expr} AS classifier_name,
                    {column_or_default("classifier_version", "'legacy'")}
                        AS classifier_version
                FROM message_labels_legacy
            )
            GROUP BY run_id, source, classifier_name, classifier_version
        """
        self.conn.execute(run_sql)

        copy_sql = f"""
            INSERT OR REPLACE INTO message_labels (
                chat_id,
                msg_id,
                category,
                topics,
                confidence,
                source,
                classifier_name,
                classifier_version,
                run_id,
                created_at,
                updated_at
            )
            SELECT
                chat_id,
                msg_id,
                category,
                {column_or_default("topics", "''")},
                {column_or_default("confidence", "0")},
                {source_expr},
                {classifier_name_expr},
                {column_or_default("classifier_version", "'legacy'")},
                {column_or_default("run_id", "'legacy'")},
                {column_or_default("created_at", "CURRENT_TIMESTAMP")},
                {column_or_default("updated_at", "CURRENT_TIMESTAMP")}
            FROM message_labels_legacy
        """
        self.conn.execute(copy_sql)
        self.conn.execute("DROP TABLE message_labels_legacy")

    def _ensure_runs_for_existing_labels(self) -> None:
        self.conn.execute(
            """
            INSERT OR IGNORE INTO classifier_runs (
                run_id,
                source,
                classifier_name,
                classifier_version,
                label_count
            )
            SELECT
                run_id,
                source,
                classifier_name,
                classifier_version,
                COUNT(*) AS label_count
            FROM message_labels
            GROUP BY run_id, source, classifier_name, classifier_version
            """
        )

    def upsert_chat(self, chat: ChatRecord) -> None:
        self.conn.execute(
            """
            INSERT INTO chats (chat_id, name, type, total_messages)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                name = excluded.name,
                type = excluded.type,
                total_messages = excluded.total_messages,
                updated_at = CURRENT_TIMESTAMP
            """,
            (chat.chat_id, chat.name, chat.type, chat.total_messages),
        )

    def upsert_messages(self, messages: list[MessageRecord]) -> int:
        before = self.conn.total_changes
        self.conn.executemany(
            """
            INSERT INTO messages (
                chat_id, msg_id, date, author, from_id, topic_id, reply_to,
                forwarded_from, text, normalized_text, has_photo, has_file,
                media_type, raw_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(chat_id, msg_id) DO UPDATE SET
                date = excluded.date,
                author = excluded.author,
                from_id = excluded.from_id,
                topic_id = excluded.topic_id,
                reply_to = excluded.reply_to,
                forwarded_from = excluded.forwarded_from,
                text = excluded.text,
                normalized_text = excluded.normalized_text,
                has_photo = excluded.has_photo,
                has_file = excluded.has_file,
                media_type = excluded.media_type,
                raw_json = excluded.raw_json
            """,
            [
                (
                    m.chat_id,
                    m.msg_id,
                    m.date,
                    m.author,
                    m.from_id,
                    m.topic_id,
                    m.reply_to,
                    m.forwarded_from,
                    m.text,
                    m.normalized_text,
                    int(m.has_photo),
                    int(m.has_file),
                    m.media_type,
                    m.raw_json,
                )
                for m in messages
            ],
        )
        self.conn.commit()
        return self.conn.total_changes - before

    def import_chat(self, chat: ChatRecord, messages: list[MessageRecord]) -> int:
        self.upsert_chat(chat)
        return self.upsert_messages(messages)

    def stats(self) -> dict[str, int]:
        chat_count = self.conn.execute("SELECT COUNT(*) FROM chats").fetchone()[0]
        message_count = self.conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        label_count = self.conn.execute("SELECT COUNT(*) FROM message_labels").fetchone()[0]
        unclassified_count = self.conn.execute(
            self.EFFECTIVE_LABELS_CTE
            + """
            SELECT COUNT(*)
            FROM messages AS m
            WHERE NOT EXISTS (
                SELECT 1
                FROM effective_labels AS el
                WHERE el.chat_id = m.chat_id
                  AND el.msg_id = m.msg_id
            )
            """
        ).fetchone()[0]
        return {
            "chats": int(chat_count),
            "messages": int(message_count),
            "labels": int(label_count),
            "unclassified": int(unclassified_count),
        }

    def messages_for_classification(self) -> list[sqlite3.Row]:
        return list(
            self.conn.execute(
                """
                SELECT chat_id, msg_id, text
                FROM messages
                ORDER BY chat_id, msg_id
                """
            )
        )

    def upsert_message_labels(self, labels: Iterable[LabelRecord]) -> int:
        label_list = list(labels)
        rows = [
            (
                label.chat_id,
                label.msg_id,
                label.category,
                ",".join(label.topics),
                label.confidence,
                label.source,
                label.classifier_name,
                label.classifier_version,
                label.run_id,
            )
            for label in label_list
        ]
        if not rows:
            return 0

        run_rows = sorted(
            {
                (
                    label.run_id,
                    label.source,
                    label.classifier_name,
                    label.classifier_version,
                )
                for label in label_list
            }
        )
        run_ids = sorted({label.run_id for label in label_list})

        try:
            self.conn.executemany(
                """
                INSERT OR IGNORE INTO classifier_runs (
                    run_id,
                    source,
                    classifier_name,
                    classifier_version
                )
                VALUES (?, ?, ?, ?)
                """,
                run_rows,
            )
            before = self.conn.total_changes
            self.conn.executemany(
                """
                INSERT INTO message_labels (
                    chat_id,
                    msg_id,
                    category,
                    topics,
                    confidence,
                    source,
                    classifier_name,
                    classifier_version,
                    run_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(
                    chat_id,
                    msg_id,
                    source,
                    classifier_name,
                    classifier_version,
                    run_id
                ) DO UPDATE SET
                    category = excluded.category,
                    topics = excluded.topics,
                    confidence = excluded.confidence,
                    run_id = excluded.run_id,
                    updated_at = CURRENT_TIMESTAMP
                """,
                rows,
            )
            changed = self.conn.total_changes - before
            for run_id in run_ids:
                self.conn.execute(
                    """
                    UPDATE classifier_runs
                    SET
                        label_count = (
                            SELECT COUNT(*)
                            FROM message_labels
                            WHERE run_id = ?
                        ),
                        completed_at = CURRENT_TIMESTAMP
                    WHERE run_id = ?
                    """,
                    (run_id, run_id),
                )
        except sqlite3.DatabaseError:
            self.conn.rollback()
            raise
        self.conn.commit()
        return changed

    def latest_classifier_run(
        self,
        *,
        source: str = "rules",
        classifier_name: str | None = None,
        classifier_version: str | None = None,
        run_id: str | None = None,
    ) -> sqlite3.Row | None:
        conditions = ["source = ?"]
        params: list[str] = [source]
        if classifier_name is not None:
            conditions.append("classifier_name = ?")
            params.append(classifier_name)
        if classifier_version is not None:
            conditions.append("classifier_version = ?")
            params.append(classifier_version)
        if run_id is not None:
            conditions.append("run_id = ?")
            params.append(run_id)

        where_clause = " AND ".join(conditions)
        return self.conn.execute(
            f"""
            SELECT
                source,
                classifier_name,
                classifier_version,
                run_id,
                label_count AS count,
                completed_at AS updated_at
            FROM classifier_runs
            WHERE {where_clause}
              AND EXISTS (
                  SELECT 1
                  FROM message_labels
                  WHERE message_labels.run_id = classifier_runs.run_id
              )
            ORDER BY id DESC
            LIMIT 1
            """,
            params,
        ).fetchone()

    def label_versions(self, limit: int = 10) -> list[sqlite3.Row]:
        return list(
            self.conn.execute(
                """
                SELECT
                    r.source,
                    r.classifier_name,
                    r.classifier_version,
                    r.run_id,
                    COUNT(l.msg_id) AS count,
                    r.completed_at AS updated_at
                FROM classifier_runs AS r
                JOIN message_labels AS l
                  ON l.run_id = r.run_id
                GROUP BY
                    r.id,
                    r.source,
                    r.classifier_name,
                    r.classifier_version,
                    r.run_id,
                    r.completed_at
                ORDER BY r.id DESC
                LIMIT ?
                """,
                (limit,),
            )
        )

    def labels_for_classifier(
        self,
        *,
        classifier_name: str,
        classifier_version: str | None = None,
        run_id: str | None = None,
        source: str = "rules",
    ) -> list[sqlite3.Row]:
        run = self.latest_classifier_run(
            source=source,
            classifier_name=classifier_name,
            classifier_version=classifier_version,
            run_id=run_id,
        )
        if run is None:
            return []

        return list(
            self.conn.execute(
                """
                SELECT
                    chat_id,
                    msg_id,
                    category,
                    topics,
                    confidence,
                    source,
                    classifier_name,
                    classifier_version,
                    run_id
                FROM message_labels
                WHERE source = ?
                  AND classifier_name = ?
                  AND classifier_version = ?
                  AND run_id = ?
                ORDER BY chat_id, msg_id
                """,
                (
                    run["source"],
                    run["classifier_name"],
                    run["classifier_version"],
                    run["run_id"],
                ),
            )
        )

    def effective_labels_for_classifier(
        self,
        *,
        classifier_name: str,
        classifier_version: str | None = None,
        run_id: str | None = None,
        source: str = "rules",
    ) -> list[sqlite3.Row]:
        run = self.latest_classifier_run(
            source=source,
            classifier_name=classifier_name,
            classifier_version=classifier_version,
            run_id=run_id,
        )
        if run is None:
            return []

        return list(
            self.conn.execute(
                """
                WITH base_labels AS (
                    SELECT
                        chat_id,
                        msg_id,
                        category,
                        topics,
                        confidence,
                        source,
                        classifier_name,
                        classifier_version,
                        run_id
                    FROM message_labels
                    WHERE source = ?
                      AND classifier_name = ?
                      AND classifier_version = ?
                      AND run_id = ?
                ),
                manual_ranked AS (
                    SELECT
                        l.chat_id,
                        l.msg_id,
                        l.category,
                        l.topics,
                        l.confidence,
                        l.source,
                        l.classifier_name,
                        l.classifier_version,
                        l.run_id,
                        ROW_NUMBER() OVER (
                            PARTITION BY l.chat_id, l.msg_id
                            ORDER BY r.id DESC,
                                     l.classifier_version DESC,
                                     l.run_id DESC
                        ) AS rank
                    FROM message_labels AS l
                    JOIN classifier_runs AS r
                      ON r.run_id = l.run_id
                     AND r.source = l.source
                     AND r.classifier_name = l.classifier_name
                     AND r.classifier_version = l.classifier_version
                    WHERE l.source = 'manual'
                ),
                manual_labels AS (
                    SELECT
                        chat_id,
                        msg_id,
                        category,
                        topics,
                        confidence,
                        source,
                        classifier_name,
                        classifier_version,
                        run_id
                    FROM manual_ranked
                    WHERE rank = 1
                ),
                effective_labels AS (
                    SELECT *
                    FROM base_labels AS b
                    WHERE NOT EXISTS (
                        SELECT 1
                        FROM manual_labels AS ml
                        WHERE ml.chat_id = b.chat_id
                          AND ml.msg_id = b.msg_id
                    )
                    UNION ALL
                    SELECT *
                    FROM manual_labels
                )
                SELECT *
                FROM effective_labels
                ORDER BY chat_id, msg_id
                """,
                (
                    run["source"],
                    run["classifier_name"],
                    run["classifier_version"],
                    run["run_id"],
                ),
            )
        )

    def effective_label_for_message(
        self,
        chat_id: str,
        msg_id: int,
    ) -> sqlite3.Row | None:
        return self.conn.execute(
            self.EFFECTIVE_LABELS_CTE
            + """
            SELECT
                chat_id,
                msg_id,
                category,
                topics,
                confidence,
                source,
                classifier_name,
                classifier_version,
                run_id
            FROM effective_labels
            WHERE chat_id = ?
              AND msg_id = ?
            LIMIT 1
            """,
            (chat_id, msg_id),
        ).fetchone()

    def review_label_candidates(
        self,
        *,
        confidence_threshold: float,
        limit: int,
        include_preview: bool = False,
    ) -> list[sqlite3.Row]:
        preview_expr = "substr(m.text, 1, 160)" if include_preview else "NULL"
        return list(
            self.conn.execute(
                self.EFFECTIVE_LABELS_CTE
                + f"""
                SELECT
                    m.chat_id,
                    m.msg_id,
                    m.date,
                    el.category,
                    el.topics,
                    el.confidence,
                    el.source,
                    el.classifier_name,
                    el.classifier_version,
                    CASE
                        WHEN el.confidence <= ? THEN 'low_confidence'
                        WHEN el.category IN ('case', 'insight', 'offtopic')
                         AND el.topics <> '' THEN 'topic_on_non_key_category'
                        ELSE 'review'
                    END AS reason,
                    {preview_expr} AS preview
                FROM messages AS m
                JOIN effective_labels AS el
                  ON el.chat_id = m.chat_id
                 AND el.msg_id = m.msg_id
                WHERE el.confidence <= ?
                   OR (
                        el.category IN ('case', 'insight', 'offtopic')
                    AND el.topics <> ''
                   )
                ORDER BY
                    el.confidence ASC,
                    m.date ASC,
                    m.msg_id ASC,
                    m.chat_id ASC
                LIMIT ?
                """,
                (confidence_threshold, confidence_threshold, limit),
            )
        )

    def review_label_candidate_count(
        self,
        *,
        confidence_threshold: float,
    ) -> int:
        return int(
            self.conn.execute(
                self.EFFECTIVE_LABELS_CTE
                + """
                SELECT COUNT(*)
                FROM messages AS m
                JOIN effective_labels AS el
                  ON el.chat_id = m.chat_id
                 AND el.msg_id = m.msg_id
                WHERE el.confidence <= ?
                   OR (
                        el.category IN ('case', 'insight', 'offtopic')
                    AND el.topics <> ''
                   )
                """,
                (confidence_threshold,),
            ).fetchone()[0]
        )

    def chat_aliases(self) -> dict[str, str]:
        rows = self.conn.execute(
            """
            SELECT DISTINCT chat_id
            FROM messages
            ORDER BY chat_id ASC
            """
        ).fetchall()
        return {
            str(row["chat_id"]): f"chat{index}"
            for index, row in enumerate(rows, start=1)
        }

    def message_exists(self, chat_id: str, msg_id: int) -> bool:
        row = self.conn.execute(
            """
            SELECT 1
            FROM messages
            WHERE chat_id = ?
              AND msg_id = ?
            LIMIT 1
            """,
            (chat_id, msg_id),
        ).fetchone()
        return row is not None

    def chat_ids_for_msg_id(self, msg_id: int) -> list[str]:
        return [
            str(row["chat_id"])
            for row in self.conn.execute(
                """
                SELECT chat_id
                FROM messages
                WHERE msg_id = ?
                ORDER BY chat_id ASC
                """,
                (msg_id,),
            )
        ]

    def label_distribution(self) -> list[sqlite3.Row]:
        return list(
            self.conn.execute(
                self.EFFECTIVE_LABELS_CTE
                + """
                SELECT category, COUNT(*) AS count
                FROM effective_labels
                GROUP BY category
                ORDER BY count DESC, category ASC
                """
            )
        )

    def deduplicated_label_frequencies(
        self,
        categories: tuple[str, ...] = ("pain", "question", "solution_ad", "tool_mention"),
    ) -> list[sqlite3.Row]:
        if not categories:
            return []

        placeholders = ",".join("?" for _ in categories)
        return list(
            self.conn.execute(
                self._frequency_cte(placeholders)
                + """
                SELECT
                    category,
                    COUNT(*) AS raw_count,
                    COUNT(DISTINCT evidence_key) AS unique_count,
                    COUNT(*) - COUNT(DISTINCT evidence_key) AS duplicate_count,
                    SUM(is_forwarded) AS forwarded_count,
                    SUM(CASE WHEN duplicate_rank > 1 THEN 1 ELSE 0 END)
                        AS repeated_count,
                    SUM(
                        CASE
                            WHEN is_forwarded = 1 OR duplicate_rank > 1 THEN 1
                            ELSE 0
                        END
                    ) AS weaker_evidence_count
                FROM ranked_messages
                GROUP BY category
                ORDER BY
                    CASE category
                        WHEN 'pain' THEN 1
                        WHEN 'question' THEN 2
                        WHEN 'solution_ad' THEN 3
                        WHEN 'tool_mention' THEN 4
                        ELSE 99
                    END,
                    category ASC
                """,
                categories,
            )
        )

    def duplicate_label_groups(
        self,
        categories: tuple[str, ...] = ("pain", "question", "solution_ad", "tool_mention"),
    ) -> list[sqlite3.Row]:
        if not categories:
            return []

        placeholders = ",".join("?" for _ in categories)
        return list(
            self.conn.execute(
                self._frequency_cte(placeholders)
                + """
                SELECT
                    category,
                    normalized_text,
                    COUNT(*) AS raw_count,
                    COUNT(*) - 1 AS duplicate_count,
                    SUM(is_forwarded) AS forwarded_count,
                    GROUP_CONCAT(msg_id, ',') AS msg_ids
                FROM labeled_messages
                WHERE normalized_text <> ''
                GROUP BY category, evidence_key
                HAVING COUNT(*) > 1
                ORDER BY category ASC, raw_count DESC, normalized_text ASC
                """,
                categories,
            )
        )

    def weak_evidence_messages(
        self,
        categories: tuple[str, ...] = ("pain", "question", "solution_ad", "tool_mention"),
    ) -> list[sqlite3.Row]:
        if not categories:
            return []

        placeholders = ",".join("?" for _ in categories)
        return list(
            self.conn.execute(
                self._frequency_cte(placeholders)
                + """
                SELECT
                    category,
                    chat_id,
                    msg_id,
                    is_forwarded,
                    CASE WHEN duplicate_rank > 1 THEN 1 ELSE 0 END AS is_repeated
                FROM ranked_messages
                WHERE is_forwarded = 1 OR duplicate_rank > 1
                ORDER BY
                    CASE category
                        WHEN 'pain' THEN 1
                        WHEN 'question' THEN 2
                        WHEN 'solution_ad' THEN 3
                        WHEN 'tool_mention' THEN 4
                        ELSE 99
                    END,
                    msg_id ASC
                """,
                categories,
            )
        )

    def messages_for_clustering(self) -> list[ClusterSourceMessage]:
        rows = list(
            self.conn.execute(
                self.EFFECTIVE_LABELS_CTE
                + """
                SELECT
                    m.chat_id,
                    m.msg_id,
                    m.date,
                    m.forwarded_from,
                    m.text,
                    m.normalized_text,
                    el.category,
                    el.topics
                FROM messages AS m
                JOIN effective_labels AS el
                  ON el.chat_id = m.chat_id
                 AND el.msg_id = m.msg_id
                ORDER BY m.date ASC, m.msg_id ASC, m.chat_id ASC
                """
            )
        )
        return [
            ClusterSourceMessage(
                chat_id=str(row["chat_id"]),
                msg_id=int(row["msg_id"]),
                date=str(row["date"]),
                category=str(row["category"]),
                topics=tuple(
                    topic
                    for topic in str(row["topics"]).split(",")
                    if topic
                ),
                text=str(row["text"]),
                normalized_text=str(row["normalized_text"]),
                forwarded_from=str(row["forwarded_from"]),
            )
            for row in rows
        ]

    def messages_for_solutions(self) -> list[SolutionSourceMessage]:
        rows = list(
            self.conn.execute(
                self.EFFECTIVE_LABELS_CTE
                + """
                SELECT
                    m.chat_id,
                    m.msg_id,
                    m.date,
                    m.author,
                    m.from_id,
                    m.forwarded_from,
                    m.text,
                    m.normalized_text,
                    el.category,
                    el.topics
                FROM messages AS m
                JOIN effective_labels AS el
                  ON el.chat_id = m.chat_id
                 AND el.msg_id = m.msg_id
                ORDER BY m.date ASC, m.msg_id ASC, m.chat_id ASC
                """
            )
        )
        return [
            SolutionSourceMessage(
                chat_id=str(row["chat_id"]),
                msg_id=int(row["msg_id"]),
                date=str(row["date"]),
                author=str(row["author"]),
                from_id=str(row["from_id"]),
                category=str(row["category"]),
                topics=tuple(
                    topic
                    for topic in str(row["topics"]).split(",")
                    if topic
                ),
                text=str(row["text"]),
                normalized_text=str(row["normalized_text"]),
                forwarded_from=str(row["forwarded_from"]),
            )
            for row in rows
        ]

    def _frequency_cte(self, category_placeholders: str) -> str:
        return (
            self.EFFECTIVE_LABELS_CTE
            + f"""
            , labeled_messages AS (
                SELECT
                    el.category,
                    m.chat_id,
                    m.msg_id,
                    m.date,
                    m.normalized_text,
                    CASE
                        WHEN m.normalized_text = ''
                        THEN m.chat_id || ':' || m.msg_id
                        ELSE m.normalized_text
                    END AS evidence_key,
                    CASE WHEN m.forwarded_from <> '' THEN 1 ELSE 0 END
                        AS is_forwarded
                FROM messages AS m
                JOIN effective_labels AS el
                  ON el.chat_id = m.chat_id
                 AND el.msg_id = m.msg_id
                WHERE el.category IN ({category_placeholders})
            ),
            ranked_messages AS (
                SELECT
                    *,
                    ROW_NUMBER() OVER (
                        PARTITION BY category, evidence_key
                        ORDER BY date ASC, msg_id ASC, chat_id ASC
                    ) AS duplicate_rank
                FROM labeled_messages
            )
            """
        )

    def latest_messages(self, limit: int = 20) -> list[sqlite3.Row]:
        return list(
            self.conn.execute(
                self.EFFECTIVE_LABELS_CTE
                + """
                SELECT
                    m.chat_id,
                    m.msg_id,
                    m.date,
                    m.author,
                    substr(m.text, 1, 160) AS preview,
                    COALESCE(el.category, 'unclassified') AS category,
                    COALESCE(el.classifier_name, '') AS classifier_name,
                    COALESCE(el.classifier_version, '') AS classifier_version
                FROM messages AS m
                LEFT JOIN effective_labels AS el
                  ON el.chat_id = m.chat_id
                 AND el.msg_id = m.msg_id
                ORDER BY m.date DESC
                LIMIT ?
                """,
                (limit,),
            )
        )
