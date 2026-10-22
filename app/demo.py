import os
import json
import hashlib
from app.blockchain.chain import Blockchain
from app.blockchain.transaction import Transaction


def print_header(title: str):
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def short_hash(h: str) -> str:
    return f"{h[:16]}...{h[-8:]}" if h else "None"


def main() -> None:
    # Используем абсолютный путь, чтобы точно знать, где файл
    db_file = os.path.abspath("demo_blockchain.json")
    ext_file = os.path.abspath("demo_external_doc.txt")

    if os.path.exists(db_file): os.remove(db_file)
    if os.path.exists(ext_file): os.remove(ext_file)

    # --- СЦЕНАРИЙ 1 ---
    print_header("1. Создание нового блокчейна с генезис-блоком")
    bc = Blockchain(storage_path=db_file)
    genesis = bc.create_genesis_block()
    print(f"Создан Блок 0 (Генезис).")
    print(f"  index:     {genesis.index}")
    print(f"  prev_hash: {genesis.prev_hash} (всегда '0' для первого)")
    print(f"  hash:      {short_hash(genesis.hash)}")

    # --- СЦЕНАРИЙ 2 ---
    print_header("2. Добавление записей и блоков, демонстрация хешей")

    tx1 = Transaction("CREATE_SHIPMENT", "SH-100", None, 1)
    block1 = bc.add_block([tx1])
    print(f"Добавлен Блок 1 с транзакцией:")
    print(json.dumps(tx1.to_dict(), indent=2, ensure_ascii=False))
    print(f"  hash Блока 1: {short_hash(block1.hash)}")
    print(f"  prev_hash Блока 1: {short_hash(block1.prev_hash)}")
    print(f"  Связь: prev_hash Блока 1 совпадает с hash Блока 0? -> {block1.prev_hash == genesis.hash}")

    tx2 = Transaction("TRANSFER_SHIPMENT", "SH-100", 1, 2)
    block2 = bc.add_block([tx2])
    print(f"\nДобавлен Блок 2. Связь: prev_hash Блока 2 совпадает с hash Блока 1? -> {block2.prev_hash == block1.hash}")
    print(f"  hash Блока 2: {short_hash(block2.hash)}")

    # --- СЦЕНАРИЙ 3 ---
    print_header("3. Сохранение, перезапуск и восстановление")
    print(f"Данные сохранены в файл: {db_file}")
    print("Имитируем перезапуск программы...")
    del bc
    bc = Blockchain.load_from_file(db_file)
    print(f"Блокчейн восстановлен из файла. Блоков в цепочке: {len(bc)}")

    # --- СЦЕНАРИЙ 4 ---
    print_header("4. Проверка валидности корректного блокчейна")
    is_valid, msg = bc.validate_chain()
    print(f"Результат проверки: {is_valid}")
    print(f"Диагностика: {msg}")

    # --- СЦЕНАРИЙ 5 ---
    print_header("5. Изменение содержимого записи (подделка)")
    print(f"До подделки: Запись в Блоке 1 = {bc.chain[1].transactions[0].event_type}")
    print(f"Хеш транзакции до: {short_hash(bc.chain[1].transactions[0].hash)}")

    bc.chain[1].transactions[0].event_type = "HACKED_EVENT"

    print(f"После подделки: Запись в Блоке 1 = {bc.chain[1].transactions[0].event_type}")
    print(f"Пересчитанный хеш транзакции: {short_hash(bc.chain[1].transactions[0].compute_hash())}")

    is_valid, msg = bc.validate_chain()
    print(f"\nРезультат проверки: {is_valid}")
    print(f"ДИАГНОСТИКА: {msg}")

    # --- СЦЕНАРИЙ 6 ---
    print_header("6. Изменение хеша предыдущего блока (разрыв)")
    bc = Blockchain.load_from_file(db_file)  # Сброс
    print("Меняем prev_hash у Блока 2 на фейковый...")
    print(f"Было: {short_hash(bc.chain[2].prev_hash)}")
    bc.chain[2].prev_hash = "fake_hash_123456789"
    bc.chain[2].hash = bc.chain[2].compute_hash()  # Пересчитываем, чтобы сам блок был валиден
    print(f"Стало: {short_hash(bc.chain[2].prev_hash)}")

    is_valid, msg = bc.validate_chain()
    print(f"\nРезультат проверки: {is_valid}")
    print(f"ДИАГНОСТИКА: {msg}")

    # --- СЦЕНАРИЙ 7 ---
    print_header("7. Проверка внешнего файла")
    with open(ext_file, "w", encoding="utf-8") as f:
        f.write("Оригинальный документ: Передано 20 кг кофе.")

    file_hash = hashlib.sha256(open(ext_file, "rb").read()).hexdigest()
    print(f"Создан файл: {os.path.basename(ext_file)}")
    print(f"Его хеш: {short_hash(file_hash)}")

    bc = Blockchain.load_from_file(db_file)  # Сброс
    tx3 = Transaction("TRANSFER_SHIPMENT", "SH-100", 2, 3, document_hash=file_hash)
    bc.add_block([tx3])
    print("Хеш файла записан в Блок 3 (в транзакцию).")

    print("\nМеняем содержимое файла на диске на 'ПОДДЕЛКА'...")
    with open(ext_file, "w", encoding="utf-8") as f:
        f.write("ПОДДЕЛКА: Передано 50 кг.")

    new_file_hash = hashlib.sha256(open(ext_file, "rb").read()).hexdigest()
    print(f"Новый хеш файла: {short_hash(new_file_hash)}")

    tx_in_block = bc.chain[3].transactions[0]
    if tx_in_block.document_hash != new_file_hash:
        print(f"\nРезультат проверки: False")
        print(
            "ДИАГНОСТИКА: Хеш файла на диске не совпадает с хешем, записанным в Блоке 3 (Запись 0). Документ был подменен.")

    # Раскомментируй строки ниже, если хочешь оставить файлы на диске после демо
    # if os.path.exists(db_file): os.remove(db_file)
    # if os.path.exists(ext_file): os.remove(ext_file)


if __name__ == "__main__":
    main()