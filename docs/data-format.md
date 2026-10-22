# Соглашение о формате данных

## Формат транзакции (Записи)
```json
{
  "event_type": "TRANSFER_SHIPMENT",
  "shipment_number": "SH-100",
  "from_user_id": 1,
  "to_user_id": 2,
  "timestamp": "2026-10-22T12:00:00+00:00",
  "document_hash": "abcdef123456...",
  "hash": "123456abcdef..."
}
{
  "index": 1,
  "timestamp": "2026-10-22T12:05:00+00:00",
  "transactions": [ ... ],
  "prev_hash": "0000...",
  "hash": "1111...",
  "nonce": 0
}
