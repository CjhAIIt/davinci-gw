"""桥接配置的校验规则。"""

from __future__ import annotations

import pytest

from davinci_gw.bridge.config import BridgeConfig, BridgeConfigError, CoreConfig, is_loopback_host


def test_default_config_is_loopback_only() -> None:
    config = BridgeConfig()
    config.validate()
    assert config.host == "127.0.0.1"
    assert config.port == 8765
    assert config.path == "/mcp"


def test_loopback_detection_covers_names_and_addresses() -> None:
    assert is_loopback_host("127.0.0.1")
    assert is_loopback_host("::1")
    assert is_loopback_host("localhost")
    assert not is_loopback_host("0.0.0.0")
    assert not is_loopback_host("192.168.1.10")


def test_non_loopback_host_requires_explicit_opt_in() -> None:
    with pytest.raises(BridgeConfigError):
        BridgeConfig(host="0.0.0.0").validate()
    BridgeConfig(host="0.0.0.0", allow_remote=True).validate()


def test_invalid_port_and_path_are_rejected() -> None:
    with pytest.raises(BridgeConfigError):
        BridgeConfig(port=70000).validate()
    with pytest.raises(BridgeConfigError):
        BridgeConfig(path="mcp").validate()


def test_core_modes_have_their_own_requirements() -> None:
    CoreConfig(mode="embedded").validate()
    with pytest.raises(BridgeConfigError):
        CoreConfig(mode="stdio").validate()
    with pytest.raises(BridgeConfigError):
        CoreConfig(mode="http", target="ftp://host").validate()
    with pytest.raises(BridgeConfigError):
        CoreConfig(mode="http", target="http://127.0.0.1:9100/mcp", timeout_seconds=0).validate()
    CoreConfig(mode="http", target="http://127.0.0.1:9100/mcp").validate()
    CoreConfig(mode="stdio", target="davinci-gw-mcp.exe").validate()


def test_effective_token_is_generated_when_missing() -> None:
    config = BridgeConfig()
    token = config.effective_token
    assert token and len(token) >= 32
    assert BridgeConfig(token="fixed-token").effective_token == "fixed-token"


def test_effective_token_stays_the_same_for_the_whole_process() -> None:
    """令牌在进程生命周期内固定：发现文件与服务端鉴权必须拿到同一个值。"""
    config = BridgeConfig()
    assert config.effective_token == config.effective_token
    assert config.token == config.effective_token
    # 不同实例使用不同令牌，避免多实例互相串用。
    assert BridgeConfig().effective_token != config.effective_token


def test_core_description_never_leaks_the_token() -> None:
    described = CoreConfig(mode="http", target="http://127.0.0.1:9100/mcp", token="secret").describe()
    assert "secret" not in str(described)
    assert described["mode"] == "http"


def test_url_for_formats_ipv6_hosts() -> None:
    assert BridgeConfig(host="127.0.0.1", port=8765).url_for() == "http://127.0.0.1:8765/mcp"
    assert BridgeConfig(host="::1", port=9000).url_for(9100) == "http://[::1]:9100/mcp"
