from dataclasses import dataclass, field
from typing import List

from .crypto import sha256
from .transaction import Transaction, utc_now_iso


@dataclass
class Block:
    index: int
    transactions: List[Transaction]
    prev_hash: str
    timestamp: str = field(default_factory=utc_now_iso)
    nonce: int = 0
    hash: str = ""

    def __post_init__(self) -> None:
        if not self.hash:
            self.hash = self.compute_hash()

    def _hashable_dict(self) -> dict:
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "transactions": [tx.to_dict() for tx in self.transactions],
            "prev_hash": self.prev_hash,
            "nonce": self.nonce,
        }

    def compute_hash(self) -> str:
        return sha256(self._hashable_dict())

    def is_valid(self) -> bool:
        return self.hash == self.compute_hash()

    def add_transaction(self, tx: Transaction) -> None:
        self.transactions.append(tx)
        self.hash = self.compute_hash()

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "transactions": [tx.to_dict() for tx in self.transactions],
            "prev_hash": self.prev_hash,
            "hash": self.hash,
            "nonce": self.nonce,
        }

    @staticmethod
    def from_dict(data: dict) -> "Block":
        return Block(
            index=data["index"],
            transactions=[Transaction.from_dict(t) for t in data["transactions"]],
            prev_hash=data["prev_hash"],
            timestamp=data["timestamp"],
            nonce=data.get("nonce", 0),
            hash=data.get("hash", ""),
        )