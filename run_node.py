import argparse
import uvicorn

from app.core.config import NodeSettings, normalize_url
from app.main import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Запуск независимой ноды blockchain_logistics")
    parser.add_argument("--node-id", default="node-1", help="Уникальный идентификатор ноды")
    parser.add_argument("--host", default="127.0.0.1", help="Хост (по умолчанию 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8001, help="Порт ноды")
    parser.add_argument("--storage", default=None, help="Путь к JSON-файлу блокчейна")
    parser.add_argument("--peers-file", default=None, help="Путь к JSON-файлу списка пиров")
    parser.add_argument("--peers", default="", help="Начальный список URL пиров через запятую")
    parser.add_argument("--sync-interval", type=float, default=5.0, help="Интервал автосинхронизации в сек (0 = выкл)")
    args = parser.parse_args()

    storage = args.storage or f"data/{args.node_id}_blockchain.json"
    peers = [normalize_url(p) for p in args.peers.split(",") if p.strip()]

    settings = NodeSettings(
        node_id=args.node_id,
        host=args.host,
        port=args.port,
        storage_path=storage,
        peers_path=args.peers_file,
        initial_peers=peers,
        sync_interval=args.sync_interval,
    )
    application = create_app(settings)
    uvicorn.run(application, host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()