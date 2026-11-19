import os
from dataclasses import dataclass, field
from typing import List, Optional


def normalize_url(url: str) -> str:
    return url.strip().rstrip("/")


@dataclass
class NodeSettings:
    node_id: str = "node-1"
    host: str = "127.0.0.1"
    port: int = 8001
    storage_path: str = "data/node1_blockchain.json"
    peers_path: Optional[str] = None
    initial_peers: List[str] = field(default_factory=list)
    sync_interval: float = 5.0
    auto_sync_on_startup: bool = True

    def __post_init__(self) -> None:
        if not self.peers_path:
            base, ext = os.path.splitext(self.storage_path)
            self.peers_path = f"{base}_peers{ext or '.json'}"

    @property
    def address(self) -> str:
        return f"http://{self.host}:{self.port}"

    @classmethod
    def from_env(cls) -> "NodeSettings":
        raw_peers = os.getenv("NODE_PEERS", "")
        peers = [normalize_url(p) for p in raw_peers.split(",") if p.strip()]
        port = int(os.getenv("NODE_PORT", "8001"))
        node_id = os.getenv("NODE_ID", f"node-{port}")
        storage_path = os.getenv("STORAGE_PATH", f"data/{node_id}_blockchain.json")
        peers_path = os.getenv("PEERS_PATH") or None
        sync_interval = float(os.getenv("NODE_SYNC_INTERVAL", "5.0"))
        auto_sync = os.getenv("NODE_AUTO_SYNC", "true").lower() not in {"0", "false", "no"}
        return cls(
            node_id=node_id,
            host=os.getenv("NODE_HOST", "127.0.0.1"),
            port=port,
            storage_path=storage_path,
            peers_path=peers_path,
            initial_peers=peers,
            sync_interval=sync_interval,
            auto_sync_on_startup=auto_sync,
        )