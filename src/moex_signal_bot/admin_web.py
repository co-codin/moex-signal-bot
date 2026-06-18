from __future__ import annotations

import html
import secrets
from collections import Counter
from typing import Annotated, Protocol

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from .access_control import ACCESS_STATUSES, TelegramUser, normalize_access_status


class AdminStore(Protocol):
    def list_telegram_users(self, *, status: str | None = None, search: str | None = None) -> list[TelegramUser]: ...

    def set_telegram_user_status(self, chat_id: int, status: str) -> None: ...

    def set_telegram_user_note(self, chat_id: int, note: str) -> None: ...


security = HTTPBasic()


def create_admin_app(store: AdminStore, *, username: str, password: str) -> FastAPI:
    app = FastAPI(title="MOEX Signal Bot Admin", docs_url=None, redoc_url=None)

    def require_auth(credentials: Annotated[HTTPBasicCredentials, Depends(security)]) -> str:
        username_ok = secrets.compare_digest(credentials.username, username)
        password_ok = secrets.compare_digest(credentials.password, password)
        if not username_ok or not password_ok:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Неверный логин или пароль.",
                headers={"WWW-Authenticate": "Basic"},
            )
        return credentials.username

    @app.get("/", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
    async def dashboard(
        request: Request,
        selected_status: str | None = None,
        q: str | None = None,
    ) -> HTMLResponse:
        status_filter = normalize_access_status(selected_status) if selected_status else None
        users = store.list_telegram_users(status=status_filter, search=q)
        all_users = store.list_telegram_users()
        return HTMLResponse(_render_dashboard(users, all_users, selected_status=status_filter, search=q or ""))

    @app.post("/users/{chat_id}/status", dependencies=[Depends(require_auth)])
    async def update_status(chat_id: int, request: Request) -> RedirectResponse:
        form = await request.form()
        store.set_telegram_user_status(chat_id, str(form.get("status", "")))
        return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)

    @app.post("/users/{chat_id}/note", dependencies=[Depends(require_auth)])
    async def update_note(chat_id: int, request: Request) -> RedirectResponse:
        form = await request.form()
        store.set_telegram_user_note(chat_id, str(form.get("note", "")))
        return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)

    return app


def _render_dashboard(
    users: list[TelegramUser],
    all_users: list[TelegramUser],
    *,
    selected_status: str | None,
    search: str,
) -> str:
    counts = Counter(user.status for user in all_users)
    rows = "\n".join(_render_user_row(user) for user in users) or (
        '<tr><td colspan="8" class="empty">Пользователи не найдены.</td></tr>'
    )
    status_options = "\n".join(
        f'<option value="{status}"{" selected" if selected_status == status else ""}>{status}</option>'
        for status in ACCESS_STATUSES
    )
    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Панель доступа MOEX Signal Bot</title>
  <style>
    :root {{
      color-scheme: light;
      font-family: Arial, sans-serif;
      background: #f6f7f9;
      color: #1f2933;
    }}
    body {{ margin: 0; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 24px; }}
    h1 {{ font-size: 28px; margin: 0 0 18px; }}
    .cards {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 18px; }}
    .card {{ background: #fff; border: 1px solid #d8dee8; border-radius: 8px; padding: 14px; }}
    .label {{ color: #52616f; font-size: 13px; }}
    .value {{ display: block; font-size: 26px; font-weight: 700; margin-top: 6px; }}
    form.filters {{ display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; }}
    input, select, button, textarea {{
      border: 1px solid #c8d1dc;
      border-radius: 6px;
      font: inherit;
      padding: 8px 10px;
      background: #fff;
    }}
    button {{ cursor: pointer; background: #143d59; color: #fff; border-color: #143d59; }}
    table {{ width: 100%; border-collapse: collapse; background: #fff; border: 1px solid #d8dee8; }}
    th, td {{ text-align: left; border-bottom: 1px solid #e5e9f0; padding: 10px; vertical-align: top; }}
    th {{ font-size: 13px; color: #52616f; background: #f9fafc; }}
    .status {{ font-weight: 700; }}
    .forms {{ display: flex; gap: 6px; flex-wrap: wrap; }}
    .note-form {{ display: flex; gap: 6px; min-width: 260px; }}
    .note-form input {{ width: 190px; }}
    .empty {{ text-align: center; color: #52616f; padding: 24px; }}
    @media (max-width: 820px) {{
      .cards {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      table {{ font-size: 14px; }}
      th:nth-child(4), td:nth-child(4), th:nth-child(5), td:nth-child(5) {{ display: none; }}
    }}
  </style>
</head>
<body>
<main>
  <h1>Панель доступа</h1>
  <section class="cards">
    <div class="card"><span class="label">Всего</span><span class="value">{len(all_users)}</span></div>
    <div class="card"><span class="label">Разрешены</span><span class="value">{counts["allowed"]}</span></div>
    <div class="card"><span class="label">Ожидают</span><span class="value">{counts["pending"]}</span></div>
    <div class="card"><span class="label">Заблокированы</span><span class="value">{counts["blocked"]}</span></div>
  </section>
  <form class="filters" method="get" action="/">
    <input type="search" name="q" value="{_escape(search)}" placeholder="chat_id, username, имя или заметка">
    <select name="selected_status">
      <option value="">Все статусы</option>
      {status_options}
    </select>
    <button type="submit">Фильтр</button>
  </form>
  <table>
    <thead>
      <tr>
        <th>chat_id</th>
        <th>Пользователь</th>
        <th>Статус</th>
        <th>Первый вход</th>
        <th>Последний вход</th>
        <th>Заметка</th>
        <th>Действия</th>
      </tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>
</main>
</body>
</html>"""


def _render_user_row(user: TelegramUser) -> str:
    username = f"@{user.username}" if user.username else "без username"
    name = " ".join(part for part in (user.first_name, user.last_name) if part)
    display_name = f'{_escape(username)}<br><span class="label">{_escape(name or "имя не указано")}</span>'
    status_forms = " ".join(_status_button(user.chat_id, status) for status in ACCESS_STATUSES if status != user.status)
    return f"""<tr>
  <td>{user.chat_id}</td>
  <td>{display_name}</td>
  <td class="status">{_escape(user.status)}</td>
  <td>{_escape(_format_dt(user.first_seen_at))}</td>
  <td>{_escape(_format_dt(user.last_seen_at))}</td>
  <td>{_escape(user.note)}</td>
  <td>
    <div class="forms">{status_forms}</div>
    <form class="note-form" method="post" action="/users/{user.chat_id}/note">
      <input name="note" value="{_escape(user.note)}" placeholder="Заметка">
      <button type="submit">Сохранить</button>
    </form>
  </td>
</tr>"""


def _status_button(chat_id: int, next_status: str) -> str:
    labels = {"allowed": "Разрешить", "blocked": "Заблокировать", "pending": "В ожидание"}
    return f"""<form method="post" action="/users/{chat_id}/status">
  <input type="hidden" name="status" value="{_escape(next_status)}">
  <button type="submit">{_escape(labels[next_status])}</button>
</form>"""


def _format_dt(value) -> str:
    if value is None:
        return "-"
    return value.isoformat(timespec="seconds")


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)
