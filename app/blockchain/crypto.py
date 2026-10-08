import hashlib
import json
from typing import Union

JSONValue = Union[dict, list, str, int, float, bool, None]


def canonical_json(data: JSONValue) -> str:
    """Каноническое JSON-представление: сортировка ключей, без пробелов."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256(data: Union[str, dict, list]) -> str:
    """SHA-256 от строки, словаря или списка."""
    payload = canonical_json(data) if isinstance(data, (dict, list)) else str(data)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()