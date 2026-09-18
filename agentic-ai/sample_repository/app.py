from user_service import get_user_name


def main() -> None:
    user_id = input("Enter user ID: ")
    name = get_user_name(user_id)

    print(f"User: {name}")


if __name__ == "__main__":
    main()