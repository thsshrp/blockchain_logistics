import os
import hashlib
from app.blockchain.chain import Blockchain
from app.blockchain.transaction import Transaction


def print_header(title: str):
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")


def main() -> None:
    db_file = "demo_blockchain.json"
    ext_file = "demo_external_doc.txt"

    if os.path.exists(db_file): os.remove(db_file)
    if os.path.exists(ext_file): os.remove(ext_file)

    print_header("1. Создание блокчейна с генезис-блоком")
    bc = Blockchain(storage_path=db_file)
    bc.create_genesis_block()
    print("Генезис-блок создан.")

    print_header("2. Добавление записей и блоков")
    tx1 = Transaction("CREATE_SHIPMENT", "SH-100", None, 1)
    bc.add_block([tx1])
    tx2 = Transaction("TRANSFER_SHIPMENT", "SH-100", 1, 2)
    bc.add_block([tx2])
    print("Добавлено 2 блока с записями.")

    print_header("3. Сохранение и восстановление")
    del bc
    bc = Blockchain.load_from_file(db_file)
    print(f"Загружено блоков: {len(bc)}")

    print_header("4. Проверка валидности")
    is_valid, msg = bc.validate_chain()
    print(f"Валидна? -> {is_valid}")
    print(f"Сообщение: {msg}")

    print_header("5. Изменение содержимого записи")
    print("Меняем event_type в Блоке 1...")
    bc.chain[1].transactions[0].event_type = "HACKED"
    is_valid, msg = bc.validate_chain()
    print(f"Валидна? -> {is_valid}")
    print(f"ПРИЧИНА: {msg}")  # Программа сама скажет, какой блок сломан

    print_header("6. Изменение хеша предыдущего блока (разрыв)")
    bc = Blockchain.load_from_file(db_file)  # Сброс
    print("Меняем prev_hash у Блока 2...")
    bc.chain[2].prev_hash = "1234567890"
    bc.chain[2].hash = bc.chain[2].compute_hash()  # Пересчитываем, чтобы сам блок был валиден
    is_valid, msg = bc.validate_chain()
    print(f"Валидна? -> {is_valid}")
    print(f"ПРИЧИНА: {msg}")

    print_header("7. Проверка внешнего файла")
    with open(ext_file, "w", encoding="utf-8") as f:
        f.write("Оригинальный документ")
    file_hash = hashlib.sha256(open(ext_file, "rb").read()).hexdigest()

    bc = Blockchain.load_from_file(db_file)  # Сброс
    # Создаем запись, привязывая к ней хеш файла
    tx3 = Transaction("TRANSFER_SHIPMENT", "SH-100", 2, 3, document_hash=file_hash)
    bc.add_block([tx3])
    print("Добавлен Блок 3 с хешем внешнего файла.")

    print("Меняем файл на диске...")
    with open(ext_file, "w", encoding="utf-8") as f:
        f.write("ПОДДЕЛКА")
    new_file_hash = hashlib.sha256(open(ext_file, "rb").read()).hexdigest()

    # Проверяем
    tx_in_block = bc.chain[3].transactions[0]
    if tx_in_block.document_hash != new_file_hash:
        print(f"Валидна? -> False")
        print("ПРИЧИНА: Хеш файла на диске не совпадает с хешем, записанным в Блоке 3 (Запись 0).")
    else:
        print("Валидна? -> True")

    if os.path.exists(db_file): os.remove(db_file)
    if os.path.exists(ext_file): os.remove(ext_file)


if __name__ == "__main__":
    main()