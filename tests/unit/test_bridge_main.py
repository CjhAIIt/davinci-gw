"""桥接命令行的配置校验与客户端发现文件。"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from davinci_gw.bridge.__main__ import (
    _discovery_token_error,
    _split_command,
    _write_descriptor,
    main,
)


def test_split_command_keeps_windows_paths_and_leading_dashes() -> None:
    command, args = _split_command('"C:\\tools\\davinci-gw-mcp.exe" -m davinci_gw.mcp')
    assert command == "C:\\tools\\davinci-gw-mcp.exe"
    assert args == ["-m", "davinci_gw.mcp"]


def test_invalid_configuration_is_rejected_before_start(capsys: object) -> None:
    code = main(["--core", "stdio", "--host", "0.0.0.0"])
    assert code == 2


def test_missing_core_target_is_rejected(capsys: object) -> None:
    assert main(["--core", "http"]) == 2


def test_remote_listener_without_tls_is_rejected(capsys: object) -> None:
    """对外监听必须加密，命令行层也要拦住明文远端。"""
    assert main([
        "--core", "stdio", "--core-target", "davinci-gw-mcp.exe",
        "--host", "0.0.0.0", "--allow-remote",
    ]) == 2
    # 只给证书不给私钥同样不成立。
    assert main([
        "--core", "stdio", "--core-target", "davinci-gw-mcp.exe",
        "--host", "0.0.0.0", "--allow-remote", "--tls-certfile", "cert.pem",
    ]) == 2


def test_no_descriptor_requires_an_explicit_token(capsys: object) -> None:
    """关掉发现文件就必须显式给令牌。

    令牌缺省时随机生成，只写在发现文件里；没有发现文件时客户端就无从
    构造 Authorization 头，每次调用都会鉴权失败。
    """
    assert _discovery_token_error(True, None) is not None
    assert _discovery_token_error(True, "fixed-token") is None
    assert _discovery_token_error(False, None) is None
    # 命令行层同样要拦住。
    assert main(["--core", "embedded", "--no-descriptor"]) == 2


def test_descriptor_file_is_written_for_client_discovery(tmp_path: Path) -> None:
    path = tmp_path / "bridge.json"
    _write_descriptor(path, {"url": "http://127.0.0.1:8765/mcp", "token": "t"})
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["url"] == "http://127.0.0.1:8765/mcp"
    assert payload["token"] == "t"


@pytest.mark.skipif(os.name != "nt", reason="Windows ACL 语义")
def test_descriptor_file_is_readable_only_by_the_current_user(tmp_path: Path) -> None:
    """发现文件里有明文令牌，其它本地账号不能读到。

    ``os.chmod(path, 0o600)`` 在 Windows 上只改只读属性，不建立
    owner-only 的 DACL——实测改完之后文件仍是 0o666，别的账号照样能读。
    这里用 icacls 核对真实的访问控制表。
    """
    path = tmp_path / "bridge.json"
    _write_descriptor(path, {"url": "http://127.0.0.1:8765/mcp", "token": "t"})

    completed = subprocess.run(
        ["icacls", str(path)], capture_output=True, text=True, encoding="utf-8",
        errors="replace", check=True,
    )
    acl = completed.stdout
    # 只应剩下当前用户自己的授权，其余继承项必须被清掉。
    assert "Everyone" not in acl
    assert "BUILTIN\\Users" not in acl
    assert "(I)" not in acl, acl
    # 内容本身仍要可读，否则客户端拿不到令牌。
    assert json.loads(path.read_text(encoding="utf-8"))["token"] == "t"
