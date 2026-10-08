import pytest

from app.blockchain.transaction import Transaction


def test_create_transaction():
    tx = Transaction(
        event_type="CREATE_SHIPMENT",
        shipment_number="SH-001",
        from_user_id=None,
        to_user_id=1,
    )
    assert tx.event_type == "CREATE_SHIPMENT"
    assert tx.shipment_number == "SH-001"


def test_invalid_event_type():
    with pytest.raises(ValueError):
        Transaction("UNKNOWN", "SH-001", None, None)


def test_roundtrip_dict():
    tx = Transaction("TRANSFER_SHIPMENT", "SH-001", 1, 2)
    restored = Transaction.from_dict(tx.to_dict())
    assert restored.to_dict() == tx.to_dict()


def test_compute_hash_is_deterministic():
    tx = Transaction("CREATE_SHIPMENT", "SH-001", None, 1, timestamp="2026-01-01T00:00:00+00:00")
    assert tx.compute_hash() == tx.compute_hash()