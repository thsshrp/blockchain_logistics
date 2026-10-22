from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from .crypto import canonical_json, sha256

ALLOWED_EVENT_TYPES = {"CREATE_SHIPMENT", "TRANSFER_SHIPMENT"}

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

@dataclass
class Transaction:
    event_type: str
    shipment_number: str
    from_user_id: Optional[int]
    to_user_id: Optional[int]
    timestamp: str = field(default_factory=utc_now_iso)
    document_hash: Optional[str] = None # Для проверки файлов (Спринт 3)
    hash: str = field(init=False)      # Собственный хеш записи (Спринт 3)

    def __post_init__(self) -> None:
        if self.event_type not in ALLOWED_EVENT_TYPES:
            raise ValueError(f"Unknown event_type: {self.event_type}")
        self.hash = self.compute_hash()

    def to_dict(self) -> dict:
        return {
            "event_type": self.event_type,
            "shipment_number": self.shipment_number,
            "from_user_id": self.from_user_id,
            "to_user_id": self.to_user_id,
            "timestamp": self.timestamp,
            "document_hash": self.document_hash,
            "hash": self.hash
        }

    def compute_hash(self) -> str:
        # Хешируем только данные, без самого поля hash
        data = {
            "event_type": self.event_type,
            "shipment_number": self.shipment_number,
            "from_user_id": self.from_user_id,
            "to_user_id": self.to_user_id,
            "timestamp": self.timestamp,
            "document_hash": self.document_hash
        }
        return sha256(data)

    @staticmethod
    def from_dict(data: dict) -> "Transaction":
        tx = Transaction(
            event_type=data["event_type"],
            shipment_number=data["shipment_number"],
            from_user_id=data.get("from_user_id"),
            to_user_id=data.get("to_user_id"),
            timestamp=data["timestamp"],
            document_hash=data.get("document_hash")
        )
        return tx