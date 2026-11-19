import json
import os
from typing import List, Optional, Tuple

from .block import Block
from .transaction import Transaction

GENESIS_TIMESTAMP = "2026-01-01T00:00:00+00:00"


class Blockchain:
    def __init__(self, storage_path: Optional[str] = None) -> None:
        self.chain: List[Block] = []
        self.storage_path = storage_path

    def __len__(self) -> int:
        return len(self.chain)

    def create_genesis_block(self, timestamp: str = GENESIS_TIMESTAMP) -> Block:
        if self.chain:
            raise ValueError("Genesis block already exists")
        genesis = Block(index=0, transactions=[], prev_hash="0", timestamp=timestamp)
        self.chain.append(genesis)
        self._autosave()
        return genesis

    def get_block(self, index: int) -> Block:
        return self.chain[index]

    def get_last_block(self) -> Optional[Block]:
        return self.chain[-1] if self.chain else None

    def add_block(self, transactions: List[Transaction]) -> Block:
        if not self.chain:
            raise ValueError("Genesis block must be created first")
        last = self.chain[-1]
        new_block = Block(
            index=len(self.chain),
            transactions=list(transactions),
            prev_hash=last.hash,
        )
        self.chain.append(new_block)
        self._autosave()
        return new_block

    def validate_incoming_block(self, block: Block) -> Tuple[bool, str, Optional[str]]:
        """Проверяет внешний блок перед добавлением в локальную цепочку."""
        if not self.chain:
            return False, "Локальная цепочка не инициализирована (нет генезис-блока).", "CHAIN_NOT_INITIALIZED"

        last = self.chain[-1]
        expected_index = last.index + 1

        if block.index < len(self.chain) and self.chain[block.index].hash == block.hash:
            return False, f"Блок {block.index} с таким хешем уже существует в цепочке.", "DUPLICATE_BLOCK"

        if block.index != expected_index:
            return (
                False,
                f"Некорректный индекс блока: ожидался {expected_index}, получен {block.index}.",
                "INVALID_BLOCK_INDEX",
            )

        if block.prev_hash != last.hash:
            return (
                False,
                f"Несовпадение prev_hash: ожидался '{last.hash}', получен '{block.prev_hash}'.",
                "PREV_HASH_MISMATCH",
            )

        for j, tx in enumerate(block.transactions):
            if not tx.is_valid():
                return (
                    False,
                    f"Блок {block.index}, транзакция {j}: хеш транзакции не совпадает с пересчитанным.",
                    "INVALID_TRANSACTION_HASH",
                )

        if not block.is_valid():
            return (
                False,
                f"Блок {block.index}: хеш блока не совпадает с пересчитанным.",
                "INVALID_BLOCK_HASH",
            )

        return True, "Блок валиден.", None

    def receive_block(self, block: Block) -> Tuple[bool, str, Optional[str]]:
        ok, msg, err_code = self.validate_incoming_block(block)
        if not ok:
            return False, msg, err_code
        self.chain.append(block)
        self._autosave()
        return True, f"Блок {block.index} успешно проверен и добавлен в цепочку.", None

    def validate_chain(self) -> Tuple[bool, str]:
        if not self.chain:
            return False, "Цепочка пуста"

        for i, block in enumerate(self.chain):
            if block.index != i:
                return False, f"Блок {i}: Некорректный индекс ({block.index})."

            if i == 0:
                if block.prev_hash != "0":
                    return False, f"Блок {i}: У генезис-блока prev_hash должен быть '0'"
            else:
                prev_block = self.chain[i - 1]
                if block.prev_hash != prev_block.hash:
                    return False, f"Блок {i}: Разрыв цепочки. prev_hash не совпадает с хешем Блока {i - 1}"

            for j, tx in enumerate(block.transactions):
                if not tx.is_valid():
                    return False, f"Блок {i}, Запись {j}: Хеш транзакции не совпадает. Запись была изменена."

            if not block.is_valid():
                return False, f"Блок {i}: Хеш блока не совпадает с пересчитанным. Блок был изменен."

        return True, "Все проверки пройдены. Цепочка валидна."

    def is_chain_valid(self) -> bool:
        return self.validate_chain()[0]

    def save_to_file(self, path: Optional[str] = None) -> None:
        target = path or self.storage_path
        if not target:
            raise ValueError("Storage path is not specified")
        parent = os.path.dirname(os.path.abspath(target))
        if parent:
            os.makedirs(parent, exist_ok=True)
        data = {"length": len(self.chain), "chain": [b.to_dict() for b in self.chain]}
        tmp_path = f"{target}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, target)

    @classmethod
    def load_from_file(cls, path: str) -> "Blockchain":
        if not os.path.exists(path):
            return cls(storage_path=path)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            raise ValueError(f"Corrupted blockchain file: {e}") from e

        bc = cls(storage_path=path)
        try:
            for block_data in data["chain"]:
                bc.chain.append(Block.from_dict(block_data))
        except (KeyError, TypeError, ValueError) as e:
            raise ValueError(f"Invalid blockchain file structure: {e}") from e

        return bc

    def _autosave(self) -> None:
        if self.storage_path:
            self.save_to_file()