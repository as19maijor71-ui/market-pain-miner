# Форма Вывода Классификации

```json
{
  "clusters": [
    {
      "title": "short problem name",
      "category": "pain",
      "marketplace": "wb|ozon|shared|unknown",
      "audience_segment": "seller|manager|agency|unknown",
      "evidence_message_ids": ["chat1:42"],
      "current_workaround": "manual spreadsheet",
      "possible_product_direction": "small bot/dashboard/report",
      "confidence": "low|medium|high"
    }
  ]
}
```

## Правило

В публичном и tracked-выводе использовать aliases и агрегаты. Raw quotes,
handles, URLs, имена участников и user IDs не копировать.
