import base64

from fastapi.testclient import TestClient

from moex_signal_bot.admin_web import create_admin_app
from moex_signal_bot.memory_storage import InMemoryWatchlistStore


def _auth(username: str = "admin", password: str = "secret") -> dict[str, str]:
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def test_admin_web_requires_auth_and_renders_dashboard():
    store = InMemoryWatchlistStore()
    store.record_telegram_user(123, username="guest")
    store.record_telegram_user(456, username="paid")
    store.set_telegram_user_status(456, "allowed")
    app = create_admin_app(store, username="admin", password="secret")
    client = TestClient(app)

    denied = client.get("/")
    ok = client.get("/", headers=_auth())

    assert denied.status_code == 401
    assert ok.status_code == 200
    assert "Панель доступа" in ok.text
    assert "guest" in ok.text
    assert "pending" in ok.text
    assert "allowed" in ok.text


def test_admin_web_updates_user_status_and_note():
    store = InMemoryWatchlistStore()
    store.record_telegram_user(123, username="guest")
    app = create_admin_app(store, username="admin", password="secret")
    client = TestClient(app)

    status_response = client.post(
        "/users/123/status",
        data={"status": "blocked"},
        headers=_auth(),
        follow_redirects=False,
    )
    note_response = client.post(
        "/users/123/note",
        data={"note": "Не оплатил доступ"},
        headers=_auth(),
        follow_redirects=False,
    )

    user = store.get_telegram_user(123)

    assert status_response.status_code == 303
    assert note_response.status_code == 303
    assert user.status == "blocked"
    assert user.note == "Не оплатил доступ"
