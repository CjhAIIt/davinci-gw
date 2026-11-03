"""桥接命令行的配置校验与客户端发现文件。"""

from __future__ import annotations

import json
from pathlib import Path

from davinci_gw.bridge.__main__ import _split_command, _write_descriptor, main


def test_split_command_keeps_windows_paths_and_leading_dashes() -> None:
    command, args = _split_command('"C:\\tools\\davinci-gw-mcp.exe" -m davinci_gw.mcp')
    assert command == "C:\\tools\\davinci-gw-mcp.exe"
    assert args == ["-m", "davinci_gw.mcp"]


def test_invalid_configuration_is_rejected_before_start(capsys: object) -> None:
    code = main(["--core", "stdio", "--host", "0.0.0.0"])
    assert code == 2


def test_missing_core_target_is_rejected(capsys: object) -> None:
    assert main(["--core", "http"]) == 2


def test_descriptor_file_is_written_for_client_discovery(tmp_path: Path) -> None:
    path = tmp_path / "bridge.json"
    _write_descriptor(path, {"url": "http://127.0.0.1:8765/mcp", "token": "t"})
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["url"] == "http://127.0.0.1:8765/mcp"
    assert payload["token"] == "t"
