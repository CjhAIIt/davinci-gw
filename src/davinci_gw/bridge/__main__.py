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
from davinci_gw.bridge.server import BRIDGE_VERSION, build_bridge_app, build_bridge_server

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


def _discovery_token_error(no_descriptor: bool, token: str | None) -> str | None:
    """关掉发现文件却不给令牌时返回错误说明。

    令牌缺省时随机生成，只写在发现文件里；关掉发现文件就等于把令牌
    藏了起来：服务能起来，但客户端无从构造 Authorization 头，每一次
    调用都会鉴权失败。
    """
    if no_descriptor and not token:
        return "使用 --no-descriptor 时必须显式提供 --token；随机生成的令牌没有其他可交付的途径。"
    return None


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


def _restrict_descriptor_permissions(path: Path) -> None:
    """把发现文件限制为仅当前用户可读。

    发现文件里写着明文访问令牌，别的本地账号能读到就等于拿到了
    Bridge 的调用权限。

    ``os.chmod(path, 0o600)`` 在 Windows 上只改只读属性，不建立
    owner-only 的 DACL——实测改完之后文件仍是 0o666，ACL 里其它用户
    照样能读。Windows 上改为用 ``icacls`` 重建访问控制表：先给当前
    用户显式授权，再去掉继承项，最后把别人残留的显式授权逐条移除，
    只留当前用户一条完全控制。

    只做 ``icacls /grant:r`` 与 ``/inheritance:r`` 是不够的：那两步
    只替换当前用户的授权并去掉继承项，文件上**已有**的显式授权
    （例如 ``Everyone:(R)``）会原样留下，别的账号照样能读到令牌。

    顺序上必须先授权再去继承：``/inheritance:r`` 会把继承项从
    访问控制表里摘掉，如果此时当前用户还没有显式授权，文件会短暂
    变成"谁都没有权限"，紧接着的写入与客户端的读取都会撞上
    ``PermissionError``。

    这里不用 PowerShell 的 ``Set-Acl``：``Set-Acl`` 属于
    ``Microsoft.PowerShell.Security`` 模块，在 PowerShell 7 环境里
    启动的 Windows PowerShell 5.1 会因模块自动加载失败而报错
    （"the module could not be loaded"）；而且它带 ``SetOwner`` 时
    需要 ``SeSecurityPrivilege``，对同一个文件重复收紧会失败，
    Bridge 重启就会因 fail-closed 直接起不来。``icacls`` 是系统自带
    的可执行文件，没有模块依赖，重复执行结果一致。

    收紧失败必须让启动失败：把明文令牌写进一个没保护的文件，
    比不写发现文件更危险。
    """
    if os.name != "nt":
        try:
            os.chmod(path, 0o600)
        except OSError:  # pragma: no cover - 权限受限的环境
            pass
        return
    sid = _current_user_sid()
    if not sid.upper().startswith("S-1-"):
        # 取不到 SID 就无法精确授权；授权给用户名可能命中域内同名账户。
        raise BridgeConfigError("无法确定当前用户的 SID，不能安全地限制发现文件的访问控制表。")
    # 授权项必须写成 *SID：icacls 把不带 * 的 "S-1-…" 当账户名解析，
    # 会报 "No mapping between account names and security IDs"。
    # 先显式授满当前用户：此后任何时刻当前用户都有权限。
    _run_icacls(path, "/grant:r", f"*{sid}:(F)")
    # 去掉继承项。当前用户已经有显式授权，去掉继承不会让他失去权限。
    _run_icacls(path, "/inheritance:r")
    # 再把别人残留的显式授权逐条摘掉（继承项已经摘干净，这里只剩显式项）。
    for principal, is_deny in _explicit_acl_principals(path):
        if _is_current_user_principal(principal):
            continue
        _run_icacls(path, "/remove:d" if is_deny else "/remove:g", principal)
    # 收尾再确认一次当前用户的授权仍在。
    _run_icacls(path, "/grant:r", f"*{sid}:(F)")


def _run_icacls(path: Path, *arguments: str) -> None:
    """执行一条 icacls 命令，失败即抛出可读的 BridgeConfigError。"""
    import subprocess

    try:
        completed = subprocess.run(
            ["icacls", str(path), *arguments], capture_output=True, timeout=30,
            text=True, encoding="utf-8", errors="replace",
        )
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover - 取决于系统环境
        raise BridgeConfigError(
            f"无法收紧发现文件的访问控制表，发现文件可能对其它本地账号可读：{exc}"
        ) from exc
    if completed.returncode != 0:
        raise BridgeConfigError(
            "无法收紧发现文件的访问控制表，发现文件可能对其它本地账号可读："
            + (completed.stdout + completed.stderr).strip()[-300:]
        )


def _explicit_acl_principals(path: Path) -> list[tuple[str, bool]]:
    """列出文件上显式授权的主体（继承项不算），返回 (主体, 是否拒绝项)。"""
    import subprocess

    try:
        completed = subprocess.run(
            ["icacls", str(path)], capture_output=True, timeout=30,
            text=True, encoding="utf-8", errors="replace",
        )
    except (OSError, subprocess.SubprocessError):  # pragma: no cover - 取决于系统环境
        return []
    principals: list[tuple[str, bool]] = []
    for line in completed.stdout.splitlines():
        line = line.strip()
        if not line or "Successfully processed" in line:
            continue
        # 每行形如 "C:\path\file USER:(F)"，权限部分跟在路径后面。
        parts = line.split(str(path), 1)
        entry = parts[1].strip() if len(parts) > 1 else line
        if not entry or "(I)" in entry:
            # 继承项由 /inheritance:r 统一摘掉，这里不重复处理。
            continue
        principal, separator, permissions = entry.rpartition(":")
        if not separator:
            continue
        principal = principal.strip()
        if not principal:
            continue
        principals.append((principal, "DENY" in permissions.upper()))
    return principals


def _is_current_user_principal(principal: str) -> bool:
    """判断访问控制表里的一个主体是不是当前用户。

    ``icacls`` 输出的是账户名（形如 ``DESKTOP-BA8OBJV\\cjh``），
    而 ``getpass.getuser()`` 只给裸用户名（``cjh``）——两者直接比较
    必然不相等，于是程序会把自己的授权也当成"别人的"摘掉，文件
    在那一瞬间变成谁都没有权限，读写都撞 ``PermissionError``。

    这里把当前用户的各种可能写法都列出来比较：完整 SID、域限定名、
    裸用户名；``whoami`` 的输出同样一并纳入。
    """
    if not principal:
        return False
    candidates = {principal.strip(), principal.strip().upper()}
    sid = _current_user_sid()
    if sid:
        candidates.add(sid.upper())
        candidates.add(f"*{sid.upper()}")
    user = _current_user_name()
    if user:
        candidates.add(user.upper())
        candidates.add(user.split("\\")[-1].upper())
    domain = os.environ.get("USERDOMAIN", "")
    if domain and user:
        candidates.add(f"{domain}\\{user}".upper())
    try:
        import subprocess

        completed = subprocess.run(
            ["whoami"], capture_output=True, timeout=30, text=True,
            encoding="utf-8", errors="replace",
        )
        account = completed.stdout.strip()
        if account:
            candidates.add(account.upper())
            candidates.add(account.split("\\")[-1].upper())
    except (OSError, subprocess.SubprocessError):  # pragma: no cover - 取决于系统环境
        pass
    return any(candidate in candidates for candidate in candidates if candidate)


def _current_user_name() -> str:
    """取当前用户的裸用户名，用于跳过自己的授权项。"""
    import getpass

    try:
        return getpass.getuser()
    except OSError:  # pragma: no cover - 取不到用户名时
        return ""


def _current_user_sid() -> str:
    """取当前用户的 SID，用于精确授权。

    ``whoami /user /fo csv /nh`` 的输出形如
    ``"DESKTOP\\user","S-1-5-21-..."``（两列，不是四列）。SID 才是
    唯一可靠的账户标识：裸用户名在域内存在同名账户时会授权给错的人。
    """
    try:
        import subprocess

        completed = subprocess.run(
            ["whoami", "/user", "/fo", "csv", "/nh"],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        for line in completed.stdout.splitlines():
            fields = [item.strip('" ') for item in line.split(",")]
            for field in fields:
                if field.upper().startswith("S-1-"):
                    return field
    except (OSError, subprocess.SubprocessError):  # pragma: no cover - 取决于系统环境
        pass
    import getpass

    try:
        return getpass.getuser()
    except OSError:  # pragma: no cover - 取不到用户名时
        # 连用户名都取不到时，交给 icacls 自己解析当前账户；
        # 这里给一个必然解析失败的占位，让授权明确失败而不是授权给错人。
        return ""


def _write_descriptor(path: Path, descriptor: dict[str, object]) -> None:
    """写出客户端发现文件，并确保只有当前用户能读。

    发现文件里有明文令牌，落盘时必须已经是 owner-only 的权限：直接
    ``write_text`` 会让文件先按父目录继承的权限落盘，写入与收紧之间
    存在一个明文令牌可被其它本地账号读取的窗口。

    Windows 上采用"受限临时文件 + 原子替换"：先把内容写进同目录下的
    临时文件并把它的权限收紧，再 ``os.replace`` 换到目标路径。
    收紧动作只作用在**临时文件**上，目标文件的访问控制表在整个过程
    里原封不动——既有发现文件已经被收紧过时，再对它执行 ``icacls``
    会短暂出现"谁都没有权限"的空窗，客户端在这个窗口里读文件会拿到
    ``PermissionError``；而先删后建则会在客户端正持有文件句柄时
    删不掉（``WinError 32``）。原子替换两条路都绕开了。

    ``os.replace`` 在同目录内是原子的，客户端读到的要么是旧文件、
    要么是完整的受限新文件，不会读到写了一半的内容。

    唯一例外是目标文件正被客户端独占打开：Windows 的 rename 要求
    目标没有打开的句柄，此时替换会报 ``WinError 5``。这种情况
    重试一小段时间即可——客户端读完就关闭句柄，通常只是几十毫秒。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(descriptor, ensure_ascii=False, indent=2)
    if os.name != "nt":
        path.write_text(content, encoding="utf-8")
        _restrict_descriptor_permissions(path)
        return
    temporary = path.with_name(path.name + ".tmp")
    try:
        if temporary.exists():
            temporary.unlink()
    except OSError:  # pragma: no cover - 残留临时文件删不掉时覆盖写入
        pass
    try:
        temporary.write_text(content, encoding="utf-8")
        _restrict_descriptor_permissions(temporary)
    except OSError as exc:
        raise BridgeConfigError(
            f"无法写入客户端发现文件 {path}：{exc}"
        ) from exc
    try:
        _replace_with_retry(temporary, path)
    finally:
        try:
            if temporary.exists():
                temporary.unlink()
        except OSError:  # pragma: no cover - 清理失败不影响主流程
            pass


def _replace_with_retry(temporary: Path, path: Path, attempts: int = 20) -> None:
    """把临时文件换到目标路径；目标正被占用时短暂重试。

    Windows 的 ``MoveFileEx`` 要求目标文件没有打开的句柄，客户端正
    在读发现文件时替换会报 ``WinError 5``。客户端读完即关，通常
    几十毫秒内就能换上，因此重试一小段时间即可。
    """
    import time

    last_error: OSError | None = None
    for attempt in range(attempts):
        try:
            os.replace(temporary, path)
            return
        except PermissionError as exc:
            last_error = exc
            time.sleep(0.05)
        except OSError as exc:  # pragma: no cover - 其它错误直接失败
            last_error = exc
            break
    raise BridgeConfigError(
        f"无法替换客户端发现文件 {path}：{last_error}"
    ) from last_error


async def _serve(config: BridgeConfig, log_level: str) -> None:
    import uvicorn

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
            try:
                _write_descriptor(config.descriptor_path, descriptor)
            except OSError as exc:
                # 端口已经监起来了，发现文件却写不出去：客户端拿不到令牌，
                # 留着服务只会让人以为能用。明确报错并退出。
                uvicorn_server.should_exit = True
                print(
                    f"桥接配置错误：无法写入客户端发现文件 {config.descriptor_path}：{exc}",
                    file=sys.stderr,
                    flush=True,
                )
                return
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
    token_error = _discovery_token_error(args.no_descriptor, args.token)
    if token_error is not None:
        print(f"桥接配置错误：{token_error}", file=sys.stderr)
        return 2
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
