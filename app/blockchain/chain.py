import json
import os
from typing import List, Optional, Tuple
from .block import Block
from .transaction import Transaction


class Blockchain:
    def __init__(self, storage_path: Optional[str] = None) -> None:
        self.chain: List[Block] = []
        self.storage_path = storage_path

    def __len__(self) -> int:
        return len(self.chain)

    def create_genesis_block(self) -> Block:
        if self.chain:
            raise ValueError("Genesis block already exists")
        genesis = Block(index=0, transactions=[], prev_hash="0")
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

    # НОВЫЙ МЕТОД ДЛЯ СПРИНТА 3
    def validate_chain(self) -> Tuple[bool, str]:
        if not self.chain:
            return False, "Цепочка пуста"

        for i, block in enumerate(self.chain):
            # a. Проверка хеша самого блока
            if not block.is_valid():
                return False, f"Блок {i}: Хеш блока не совпадает с пересчитанным. Блок был изменен."

            # b. Проверка связи с предыдущим блоком
            if i == 0:
                if block.prev_hash != "0":
                    return False, f"Блок {i}: У генезис-блока prev_hash должен быть '0'"
            else:
                prev_block = self.chain[i - 1]
                if block.prev_hash != prev_block.hash:
                    return False, f"Блок {i}: Разрыв цепочки. prev_hash не совпадает с хешем Блока {i - 1}"

            # c. Проверка хешей каждой записи внутри блока
            for j, tx in enumerate(block.transactions):
                if tx.hash != tx.compute_hash():
                    return False, f"Блок {i}, Запись {j}: Хеш транзакции не совпадает. Запись была изменена."

        return True, "Все проверки пройдены. Цепочка валидна."

    def is_chain_valid(self) -> bool:
        # Оставляем для обратной совместимости
        return self.validate_chain()[0]

    def save_to_file(self, path: Optional[str] = None) -> None:
        target = path or self.storage_path
        if not target:
            raise ValueError("Storage path is not specified")
        data = {"length": len(self.chain), "chain": [b.to_dict() for b in self.chain]}
        with open(target, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

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
        except (KeyError, TypeError) as e:
            raise ValueError(f"Invalid blockchain file structure: {e}") from e

        return bc

    def _autosave(self) -> None:
        if self.storage_path:
            self.save_to_file()