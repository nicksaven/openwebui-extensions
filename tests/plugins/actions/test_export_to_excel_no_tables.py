import asyncio
import importlib.util
import sys
import types
from pathlib import Path

import pytest


PLUGIN_DIR = (
    Path(__file__).resolve().parents[3]
    / "plugins"
    / "actions"
    / "export_to_excel"
)


def _load_plugin(monkeypatch, filename: str):
    fastapi = types.ModuleType("fastapi")
    open_webui = types.ModuleType("open_webui")
    models = types.ModuleType("open_webui.models")
    chats = types.ModuleType("open_webui.models.chats")
    users = types.ModuleType("open_webui.models.users")
    utils = types.ModuleType("open_webui.utils")
    chat_utils = types.ModuleType("open_webui.utils.chat")

    class HTTPException(Exception):
        def __init__(self, status_code, detail):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    fastapi.FastAPI = lambda: object()
    fastapi.HTTPException = HTTPException

    chats.Chats = object
    users.Users = object

    async def generate_chat_completion(*args, **kwargs):
        return {}

    chat_utils.generate_chat_completion = generate_chat_completion

    for name, module in {
        "fastapi": fastapi,
        "open_webui": open_webui,
        "open_webui.models": models,
        "open_webui.models.chats": chats,
        "open_webui.models.users": users,
        "open_webui.utils": utils,
        "open_webui.utils.chat": chat_utils,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)

    module_name = f"test_{Path(filename).stem}"
    spec = importlib.util.spec_from_file_location(module_name, PLUGIN_DIR / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("filename", ["export_to_excel.py", "export_to_excel_cn.py"])
def test_plain_text_returns_localized_warning_instead_of_http_error(
    monkeypatch, filename
):
    module = _load_plugin(monkeypatch, filename)
    events = []

    async def emit(event):
        events.append(event)

    result = asyncio.run(
        module.Action().action(
            {"messages": [{"role": "assistant", "content": "Только обычный текст."}]},
            __user__={"id": "user-1", "name": "User", "language": "ru-RU"},
            __event_emitter__=emit,
        )
    )

    expected = (
        "Нет возможности выгрузить текст без таблиц в Excel. "
        "Для начала сформируйте таблицу."
    )
    assert result == {"message": expected, "status": "warning"}
    assert any(
        event == {
            "type": "notification",
            "data": {"type": "warning", "content": expected},
        }
        for event in events
    )
    assert not any(
        event.get("type") == "notification"
        and event.get("data", {}).get("type") == "error"
        for event in events
    )
    assert any(
        event.get("type") == "status" and event.get("data", {}).get("done") is True
        for event in events
    )
