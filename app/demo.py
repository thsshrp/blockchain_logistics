import os
import hashlib
from app.blockchain.chain import Blockchain
from app.blockchain.transaction import Transaction


def print_header(title: str):
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")


def main() -> None:
    db_file = "demo_blockchain.json"
    ext_file = "demo_external_doc.txt"

    # Очистка перед запуском
    if os.path.exists(db_file):
        os.remove(db_file)
    if os.path.exists(ext_file):
        os.remove(ext_file)

    # 1. Создание блокчейна
    print_header("1. Создание нового блокчейна с генезис-блоком")
    bc = Blockchain(storage_path=db_file)
    bc.create_genesis_block()
    print(f"Создан генезис-блок (index=0).")
    print(f"Хеш: {bc.chain[0].hash[:20]}...")

    # 2. Добавление записей и блоков
    print_header("2. Добавление нескольких записей и блоков")
    tx1 = Transaction("CREATE_SHIPMENT", "SH-100", None, 1)
    bc.add_block([tx1])
    print(f"Добавлен Блок 1. Хеш: {bc.chain[1].hash[:20]}...")
    print(f"Prev_hash Блока 1: {bc.chain[1].prev_hash[:20]}... (совпадает с Блоком 0)")

    tx2 = Transaction("TRANSFER_SHIPMENT", "SH-100", 1, 2)
    bc.add_block([tx2])
    print(f"Добавлен Блок 2. Хеш: {bc.chain[2].hash[:20]}...")
    print(f"Prev_hash Блока 2: {bc.chain[2].prev_hash[:20]}... (совпадает с Блоком 1)")

    # 3. Сохранение и загрузка
    print_header("3. Сохранение, перезапуск и восстановление")
    print(f"Блокчейн автоматически сохранен в файл {db_file}")
    print("Имитируем перезапуск программы...")
    del bc  # удаляем из памяти
    bc = Blockchain.load_from_file(db_file)
    print(f"Блокчейн загружен с диска. Длина цепочки: {len(bc)}")

    # 4. Проверка валидности
    print_header("4. Проверка валидности корректного блокчейна")
    is_valid = bc.is_chain_valid()
    print(f"Цепочка валидна? -> {is_valid}")

    # 5. Изменение содержимого записи
    print_header("5. Изменение записи и обнаружение нарушения")
    print("Вносим изменения в транзакцию внутри Блока 1 (меняем event_type)...")
    bc.chain[1].transactions[0].event_type = "HACKED"
    is_valid = bc.is_chain_valid()
    print(f"Цепочка валидна? -> {is_valid}")
    print("ПРИЧИНА: Хеш Блока 1 не совпадает с пересчитанным (блок был изменен).")

    # 6. Изменение хеша предыдущего блока
    print_header("6. Изменение хеша предыдущего блока (разрыв)")
    print("Восстанавливаем чистую цепочку...")
    bc = Blockchain.load_from_file(db_file)

    print("Меняем prev_hash у Блока 2 и пересчитываем хеш самого Блока 2...")
    bc.chain[2].prev_hash = "1234567890abcdef"
    bc.chain[2].hash = bc.chain[2].compute_hash()  # чтобы блок сам по себе был "валидным"

    is_valid = bc.is_chain_valid()
    print(f"Цепочка валидна? -> {is_valid}")
    print("ПРИЧИНА: prev_hash Блока 2 не совпадает с хешем Блока 1 (разрыв связи).")

    # 7. Проверка внешнего файла
    print_header("7. Проверка внешнего файла (документа)")
    with open(ext_file, "w", encoding="utf-8") as f:
        f.write("Оригинальный документ: Кофе, 20 кг.")

    original_hash = hashlib.sha256(open(ext_file, "rb").read()).hexdigest()
    print(f"Создан файл. Его хеш: {original_hash[:20]}...")
    print("Добавляем этот хеш в новый блок...")

    bc = Blockchain.load_from_file(db_file)  # чистая цепочка
    tx3 = Transaction("TRANSFER_SHIPMENT", "SH-100", 2, 3)
    block3 = bc.add_block([tx3])
    # для демо сохраняем хеш файла в атрибут блока (в реальности это было бы в транзакции)
    setattr(block3, "document_hash", original_hash)

    print("Изменяем содержимое файла на диске...")
    with open(ext_file, "w", encoding="utf-8") as f:
        f.write("ПОДДЕЛКА: Кофе, 50 кг.")

    new_hash = hashlib.sha256(open(ext_file, "rb").read()).hexdigest()
    print(f"Новый хеш файла: {new_hash[:20]}...")
    print(f"Хеши совпадают? -> {original_hash == new_hash}")
    print("ПРИЧИНА: Хеш файла на диске не совпадает с тем, что записан в блокчейне.")

    # Очистка
    if os.path.exists(db_file): os.remove(db_file)
    if os.path.exists(ext_file): os.remove(ext_file)


if __name__ == "__main__":
    main()