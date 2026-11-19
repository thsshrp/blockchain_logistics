import threading
from typing import Dict, List, Optional, Tuple
import httpx

from app.blockchain.block import Block
from app.blockchain.chain import Blockchain
from app.blockchain.transaction import Transaction
from app.core.config import NodeSettings, normalize_url


class NodeServiceError(Exception):
    def __init__(self, status_code: int, error_code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.message = message


class NodeService:
    def __init__(
        self,
        settings: NodeSettings,
        http_transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        self.settings = settings
        self._lock = threading.RLock()
        self._http_transport = http_transport
        self.peers: List[str] = []

        self.blockchain = Blockchain.load_from_file(settings.storage_path)
        if len(self.blockchain) == 0:
            self.blockchain.create_genesis_block()

        for peer in settings.initial_peers:
            normalized = normalize_url(peer)
            if normalized and normalized != self.settings.address and normalized not in self.peers:
                self.peers.append(normalized)

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=5.0, transport=self._http_transport)

    # --- Состояние локальной ноды ---

    def get_info(self) -> dict:
        with self._lock:
            is_valid, msg = self.blockchain.validate_chain()
            last = self.blockchain.get_last_block()
            genesis = self.blockchain.get_block(0)
            return {
                "node_id": self.settings.node_id,
                "address": self.settings.address,
                "storage_path": self.settings.storage_path,
                "chain_length": len(self.blockchain),
                "last_block_index": last.index if last else -1,
                "last_block_hash": last.hash if last else "",
                "genesis_hash": genesis.hash,
                "is_valid": is_valid,
                "validation_message": msg,
                "peers": list(self.peers),
            }

    def get_all_blocks(self) -> List[dict]:
        with self._lock:
            return [b.to_dict() for b in self.blockchain.chain]

    def get_block(self, index: int) -> dict:
        with self._lock:
            if index < 0 or index >= len(self.blockchain):
                raise NodeServiceError(404, "BLOCK_NOT_FOUND", f"Блок с индексом {index} не найден.")
            return self.blockchain.get_block(index).to_dict()

    def get_latest_block(self) -> dict:
        with self._lock:
            last = self.blockchain.get_last_block()
            if not last:
                raise NodeServiceError(404, "CHAIN_EMPTY", "Цепочка пуста.")
            return last.to_dict()

    def validate_chain(self) -> Tuple[bool, str, int]:
        with self._lock:
            ok, msg = self.blockchain.validate_chain()
            return ok, msg, len(self.blockchain)

    # --- Создание и приём блоков ---

    def create_local_block(self, tx_inputs: List[dict]) -> dict:
        with self._lock:
            transactions: List[Transaction] = []
            try:
                for item in tx_inputs:
                    transactions.append(
                        Transaction(
                            event_type=item["event_type"],
                            shipment_number=item["shipment_number"],
                            from_user_id=item.get("from_user_id"),
                            to_user_id=item.get("to_user_id"),
                            document_hash=item.get("document_hash"),
                        )
                    )
            except (KeyError, TypeError, ValueError) as exc:
                raise NodeServiceError(400, "INVALID_TRANSACTION", str(exc)) from exc

            block = self.blockchain.add_block(transactions)
            return block.to_dict()

    def receive_external_block(self, block_data: dict) -> dict:
        with self._lock:
            try:
                block = Block.from_dict(block_data)
            except (KeyError, TypeError, ValueError) as exc:
                raise NodeServiceError(
                    400,
                    "INVALID_BLOCK_FORMAT",
                    f"Некорректный формат блока или транзакции: {exc}",
                ) from exc

            ok, msg, err_code = self.blockchain.receive_block(block)
            if not ok:
                status = 409 if err_code in {"DUPLICATE_BLOCK", "INVALID_BLOCK_INDEX", "PREV_HASH_MISMATCH"} else 400
                raise NodeServiceError(status, err_code or "INVALID_BLOCK", msg)

            return {"status": "accepted", "message": msg, "block": block.to_dict()}

    # --- Сетевое взаимодействие с другими нодами ---

    async def register_peer(
        self,
        peer_url: str,
        verify_connection: bool = True,
        bidirectional: bool = False,
    ) -> dict:
        normalized = normalize_url(peer_url)
        if not normalized.startswith(("http://", "https://")):
            raise NodeServiceError(400, "INVALID_PEER_URL", "URL пира должен начинаться с http:// или https://")
        if normalized == self.settings.address:
            raise NodeServiceError(400, "SELF_PEER_FORBIDDEN", "Нельзя добавить текущую ноду саму к себе в пиры.")

        peer_info = None
        if verify_connection:
            peer_info = await self.inspect_peer(normalized)
            local_genesis = self.blockchain.get_block(0).hash
            if peer_info["genesis_hash"] != local_genesis:
                raise NodeServiceError(
                    409,
                    "GENESIS_MISMATCH",
                    "Несовместимая сеть: генезис-блок удалённой ноды не совпадает с локальным.",
                )

        with self._lock:
            if normalized not in self.peers:
                self.peers.append(normalized)

        if bidirectional:
            try:
                async with self._client() as client:
                    await client.post(
                        f"{normalized}/api/v1/peers/register",
                        json={
                            "url": self.settings.address,
                            "verify_connection": False,
                            "bidirectional": False,
                        },
                    )
            except httpx.HTTPError:
                pass

        return {
            "status": "registered",
            "peer_url": normalized,
            "peers": list(self.peers),
            "peer_info": peer_info,
        }

    def remove_peer(self, peer_url: str) -> List[str]:
        normalized = normalize_url(peer_url)
        with self._lock:
            self.peers = [p for p in self.peers if p != normalized]
            return list(self.peers)

    async def inspect_peer(self, peer_url: str) -> dict:
        normalized = normalize_url(peer_url)
        try:
            async with self._client() as client:
                resp = await client.get(f"{normalized}/api/v1/node/info")
        except httpx.HTTPError as exc:
            raise NodeServiceError(
                502,
                "PEER_UNREACHABLE",
                f"Не удалось подключиться к ноде {normalized}: {exc}",
            ) from exc

        if resp.status_code != 200:
            raise NodeServiceError(
                502,
                "PEER_BAD_RESPONSE",
                f"Нода {normalized} вернула HTTP {resp.status_code}",
            )

        data = resp.json()
        local_genesis = self.blockchain.get_block(0).hash
        data["compatible_genesis"] = data.get("genesis_hash") == local_genesis
        data["height_diff"] = data.get("chain_length", 0) - len(self.blockchain)
        return data

    async def broadcast_block(self, block_index: int, target_peer: Optional[str] = None) -> List[dict]:
        block_dict = self.get_block(block_index)
        targets = [normalize_url(target_peer)] if target_peer else list(self.peers)
        results: List[dict] = []

        async with self._client() as client:
            for peer in targets:
                try:
                    resp = await client.post(f"{peer}/api/v1/blocks/receive", json=block_dict)
                    payload = resp.json() if resp.content else {}
                    if resp.status_code in (200, 201):
                        results.append(
                            {
                                "peer_url": peer,
                                "status": "accepted",
                                "http_status": resp.status_code,
                                "message": payload.get("message", "Блок принят."),
                                "error_code": None,
                            }
                        )
                    else:
                        detail = payload.get("detail", payload)
                        msg = detail.get("message") if isinstance(detail, dict) else str(detail)
                        code = detail.get("error_code") if isinstance(detail, dict) else "REJECTED"
                        results.append(
                            {
                                "peer_url": peer,
                                "status": "rejected",
                                "http_status": resp.status_code,
                                "message": msg,
                                "error_code": code,
                            }
                        )
                except httpx.HTTPError as exc:
                    results.append(
                        {
                            "peer_url": peer,
                            "status": "unreachable",
                            "http_status": None,
                            "message": f"Нода недоступна: {exc}",
                            "error_code": "PEER_UNREACHABLE",
                        }
                    )
        return results

    async def fetch_block_from_peer(self, peer_url: str, block_index: Optional[int] = None) -> dict:
        normalized = normalize_url(peer_url)
        target_index = block_index if block_index is not None else len(self.blockchain)

        try:
            async with self._client() as client:
                resp = await client.get(f"{normalized}/api/v1/blocks/{target_index}")
        except httpx.HTTPError as exc:
            raise NodeServiceError(
                502,
                "PEER_UNREACHABLE",
                f"Не удалось запросить блок у {normalized}: {exc}",
            ) from exc

        if resp.status_code == 404:
            raise NodeServiceError(
                404,
                "REMOTE_BLOCK_NOT_FOUND",
                f"На ноде {normalized} отсутствует блок с индексом {target_index}.",
            )
        if resp.status_code != 200:
            raise NodeServiceError(
                502,
                "PEER_BAD_RESPONSE",
                f"Нода {normalized} вернула HTTP {resp.status_code} при запросе блока {target_index}.",
            )

        remote_block = resp.json()
        return self.receive_external_block(remote_block)