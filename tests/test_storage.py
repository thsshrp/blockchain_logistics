import json

import pytest

from app.blockchain.chain import Blockchain
from app.blockchain.transaction import Transaction


def test_save_and_load(tmp_path):
    path = tmp_path / "chain.json"
    bc = Blockchain(storage_path=str(path))
    bc.create_genesis_block()
    bc.add_block([Transaction("TRANSFER_SHIPMENT", "SH-1", 1, 2)])

    loaded = Blockchain.load_from_file(str(path))
    assert len(loaded) == 2
    assert loaded.is_chain_valid()
    assert loaded.get_block(1).to_dict() == bc.get_block(1).to_dict()


def test_load_missing_file_returns_empty(tmp_path):
    path = tmp_path / "nonexistent.json"
    bc = Blockchain.load_from_file(str(path))
    assert len(bc) == 0


def test_load_corrupted_file_raises(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError):
        Blockchain.load_from_file(str(path))


def test_autosave(tmp_path):
    path = tmp_path / "chain.json"
    bc = Blockchain(storage_path=str(path))
    bc.create_genesis_block()
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["length"] == 1