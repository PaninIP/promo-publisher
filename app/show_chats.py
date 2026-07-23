from app.chats import load_chats


def main() -> None:
    chats = load_chats()

    if not chats:
        print("Список бесед пуст.")
        return

    print()
    print("Список получателей:")
    print("-" * 80)

    for index, chat in enumerate(chats, start=1):
        status = "ВКЛ" if chat.enabled else "ВЫКЛ"

        print(
            f"{index:<3} | "
            f"{status:<4} | "
            f"{str(chat.target):<22} | "
            f"{chat.name}"
        )

    print("-" * 80)
    print(f"Всего: {len(chats)}")
    print(
        "Активных:",
        sum(chat.enabled for chat in chats),
    )


if __name__ == "__main__":
    main()