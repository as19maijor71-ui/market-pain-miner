# Playbook: Update From New Export

## Goal

Process a newer Telegram export without rebuilding everything from scratch.

## Steps

1. Import the new `result.json`.
2. Upsert messages by `(chat_id, msg_id)`.
3. Classify only new or unclassified messages.
4. Update aggregate reports.
5. Re-score affected opportunity cards.
6. Add a retrospective if the update changes product direction.

## Rule

Never duplicate messages. The database primary key is `chat_id + msg_id`.

