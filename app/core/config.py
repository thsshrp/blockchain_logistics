import os
from dataclasses import dataclass, field
from typing import List


def normalize_url(url: str) -> str:
    return url.strip().rstrip("/")


@dataclass
class NodeSettings:
    node_id: str = "node-1"
    host: str = "127.0.0.1"
    port: int = 8001
    storage_path: str = "data/node1_blockchain.json"
    initial_peers: List[str] = field(default_factory=list)

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
        return cls(
            node_id=node_id,
            host=os.getenv("NODE_HOST", "127.0.0.1"),
            port=port,
            storage_path=storage_path,
            initial_peers=peers,
        )