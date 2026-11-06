"""桥接服务命令行入口。

用法示例::

    python -m davinci_gw.bridge --core embedded
    python -m davinci_gw.bridge --core stdio --core-target "C:\\tools\\davinci-gw-mcp.exe"
    python -m davinci_gw.bridge --core http --core-target http://127.0.0.1:9100/mcp
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import shlex
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from davinci_gw.bridge.config import BridgeConfig, BridgeConfigError, CoreConfig, is_loopback_host
from davinci_gw.bridge.core import build_core
from davinci_gw.bridge.server import BRIDGE_VERSION, build_bridge_server

LOGGER = logging.getLogger("davinci_gw.bridge")

DEFAULT_DESCRIPTOR_NAME = "bridge.json"


def _split_command(command: str) -> tuple[str, list[str]]:
    """把整串命令行拆成可执行文件与参数，保留 Windows 路径中的反斜杠。"""
    tokens = [token.strip('"') for token in shlex.split(command, posix=False)]
    tokens = [token for token in tokens if token]
    if not tokens:
        raise BridgeConfigError("核心命令行不能为空。")
    return tokens[0], tokens[1:]


def _parse_env(items: Sequence[str]) -> dict[str, str]:
    """解析 KEY=VALUE 形式的核心环境变量。"""
    environment: dict[str, str] = {}
    for item in items:
        name, separator, value = item.partition("=")
        if not separator or not name:
            raise BridgeConfigError(f"核心环境变量格式无效：{item}")
        environment[name] = value
    return environment


def _default_descriptor_path() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "DaVinciGW" / DEFAULT_DESCRIPTOR_NAME


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="davinci-gw-bridge", description="DaVinci 网关路由桥接服务")
    parser.add_argument("--core", choices=("embedded", "stdio", "http"), default="embedded",
                        help="核心形态：embedded=进程内，stdio=独立子进程，http=内网服务")
    parser.add_argument("--core-command", default=None,
                        help="stdio 核心的完整命令行，例如 \"C:\\path\\python.exe -m davinci_gw.mcp\"")
    parser.add_argument("--core-target", default=None, help="核心目标：stdio 模式为可执行文件，http 模式为 URL")
    parser.add_argument("--core-arg", action="append", default=[],
                        help="stdio 模式的核心参数；参数以 - 开头时使用 --core-arg=-m 形式")
    parser.add_argument("--core-env", action="append", default=[], metavar="KEY=VALUE",
                        help="stdio 模式核心进程的环境变量，可重复")
    parser.add_argument("--core-token", default=None, help="http 模式访问核心所需的令牌")
    parser.add_argument("--core-timeout", type=float, default=3600.0, help="核心调用超时秒数")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址，默认仅本机可达")
    parser.add_argument("--port", type=int, default=8765, help="监听端口，0 表示由系统分配")
    parser.add_argument("--path", default="/mcp", help="MCP 端点路径")
    parser.add_argument("--token", default=None, help="桥接访问令牌；缺省时随机生成")
    parser.add_argument("--descriptor", default=None, help="客户端发现文件路径")
    parser.add_argument("--no-descriptor", action="store_true", help="不写客户端发现文件")
    parser.add_argument("--allow-remote", action="store_true", help="允许非回环监听；必须显式开启")
    parser.add_argument("--tls-certfile", default=None, help="对外监听时的 TLS 证书路径")
    parser.add_argument("--tls-keyfile", default=None, help="对外监听时的 TLS 私钥路径")
    parser.add_argument("--allow-remote-insecure", action="store_true",
                        help="对外监听时不启用 TLS；仅在端口已置于受信加密隧道之后时使用")
    parser.add_argument("--allowed-host", action="append", default=[], metavar="HOST",
                        help="客户端实际使用的主机名或 IP，可重复；绑定全部接口时用于 Host 白名单")
    parser.add_argument("--public-host", default=None,
                        help="对外通告的客户端可达主机名或 IP；绑定全部接口时用它替代 0.0.0.0")
    parser.add_argument("--log-level", default="INFO", help="日志级别")
    return parser.parse_args(argv)


def _bound_port(server: Any, fallback: int) -> int:
    """读取实际绑定的端口；端口为 0 时由系统分配。"""
    for http_server in getattr(server, "servers", []) or []:
        for sock in getattr(http_server, "sockets", []) or []:
            try:
                return int(sock.getsockname()[1])
            except OSError:  # pragma: no cover - 极端平台差异
                continue
    return fallback


def _write_descriptor(path: Path, descriptor: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(descriptor, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:  # pragma: no cover - Windows 上权限语义不同
        pass


async def _serve(config: BridgeConfig, log_level: str) -> None:
    import uvicorn

    from davinci_gw.bridge.server import build_bridge_app

    core = build_core(config.core)
    # 端口为 0 时由系统分配实际端口；能力接口要用真实端口，
    # 否则客户端拿到的端点是 :0，连不上。
    bound_port: dict[str, int] = {}

    def current_port() -> int | None:
        return bound_port.get("port")

    app = build_bridge_app(core, config=config, port_provider=current_port)
    uvicorn_config = uvicorn.Config(
        app, host=config.host, port=config.port, log_level=log_level.lower(), access_log=False,
        ssl_certfile=config.tls_certfile, ssl_keyfile=config.tls_keyfile,
    )
    uvicorn_server = uvicorn.Server(uvicorn_config)
    task = asyncio.create_task(uvicorn_server.serve())
    try:
        while not uvicorn_server.started:
            if task.done():
                task.result()
                return
            await asyncio.sleep(0.05)
        port = _bound_port(uvicorn_server, config.port)
        bound_port["port"] = port
        descriptor = {
            "schema_version": "1.0",
            "name": "davinci-gw-bridge",
            "version": BRIDGE_VERSION,
            "pid": os.getpid(),
            "host": config.host,
            "port": port,
            "path": config.path,
            "url": config.url_for(port),
            "token": config.effective_token,
            "core": config.core.describe(),
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        if config.descriptor_path is not None:
            _write_descriptor(config.descriptor_path, descriptor)
        print(f"桥接服务已就绪：{descriptor['url']}", flush=True)
        if config.descriptor_path is not None:
            print(f"客户端发现文件：{config.descriptor_path}", flush=True)
        if not config.tls_enabled and not is_loopback_host(config.host):
            print(
                "警告：当前对外监听未启用 TLS，令牌与路由结果以明文传输；"
                "请确保该端口已置于受信加密隧道之后。",
                flush=True,
            )
        if config.wildcard_bind and not config.public_host:
            print(
                "警告：已绑定到全部接口但未指定 --public-host，"
                f"对外通告的地址为 {config.advertised_host}，远端客户端无法连接；"
                "请用 --public-host 指定客户端可达的主机名或 IP。",
                flush=True,
            )
        await task
    finally:
        await core.aclose()


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s|%(levelname)s|%(name)s|%(message)s",
    )
    try:
        core_env = _parse_env(args.core_env)
    except BridgeConfigError as exc:
        print(f"桥接配置错误：{exc}", file=sys.stderr)
        return 2
    core_config = CoreConfig(
        mode=args.core,
        target=args.core_target,
        args=tuple(args.core_arg),
        env=core_env,
        token=args.core_token,
        timeout_seconds=args.core_timeout,
    )
    if args.core_command:
        try:
            command, command_args = _split_command(args.core_command)
        except BridgeConfigError as exc:
            print(f"桥接配置错误：{exc}", file=sys.stderr)
            return 2
        core_config = CoreConfig(
            mode=args.core,
            target=core_config.target or command,
            args=tuple(command_args) + core_config.args,
            env=core_config.env,
            token=core_config.token,
            timeout_seconds=core_config.timeout_seconds,
        )
    descriptor_path = None if args.no_descriptor else (
        Path(args.descriptor) if args.descriptor else _default_descriptor_path()
    )
    config = BridgeConfig(
        host=args.host,
        port=args.port,
        path=args.path,
        token=args.token,
        core=core_config,
        descriptor_path=descriptor_path,
        allow_remote=args.allow_remote,
        tls_certfile=args.tls_certfile,
        tls_keyfile=args.tls_keyfile,
        allow_remote_insecure=args.allow_remote_insecure,
        allowed_hosts=tuple(args.allowed_host),
        public_host=args.public_host,
    )
    try:
        config.validate()
    except BridgeConfigError as exc:
        print(f"桥接配置错误：{exc}", file=sys.stderr)
        return 2
    try:
        asyncio.run(_serve(config, args.log_level))
    except KeyboardInterrupt:  # pragma: no cover - 交互式退出
        return 130
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
