# SQLite Schema

## chats

- `chat_id`: normalized Telegram chat id.
- `name`: chat name from export.
- `type`: Telegram export chat type.
- `total_messages`: number of content messages in import.

## messages

Primary key: `(chat_id, msg_id)`.

Important fields:

- `date`
- `author`
- `from_id`
- `topic_id`
- `reply_to`
- `forwarded_from`
- `text`
- `normalized_text`
- `has_photo`
- `has_file`
- `media_type`
- `raw_json`

## message_labels

Stores classifications by source:

- `category`
- `topics`
- `confidence`
- `source`
