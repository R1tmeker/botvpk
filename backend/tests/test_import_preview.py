from app.routers.admin.imports import normalize_import_row, read_import_rows


def test_csv_import_supports_russian_headers() -> None:
    rows = read_import_rows(
        "users.csv",
        "Телеграм;ФИО;Роль;Статус\n12345;Иван Иванов;participant;active\n".encode(),
    )

    assert normalize_import_row(rows[0]) == {
        "telegram_id": 12345,
        "username": None,
        "full_name": "Иван Иванов",
        "squad_id": None,
        "role_code": "PARTICIPANT",
        "status_code": "ACTIVE",
    }
