from user_service import get_user_name


def test_get_existing_user() -> None:
    assert get_user_name("1") == "Theo"