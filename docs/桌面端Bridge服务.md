# 桌面端 Bridge 服务

Bridge 在**内部端口**上提供 MCP 端点，把客户端请求转发到**独立核心**。
它让桌面客户端（C#、Electron、PySide6 或任意 MCP 客户端）不再随包携带核心代码，
核心可以单独升级，客户端只负责交互。

Bridge 不实现任何路由规则，也不改变现有 MCP 服务的边界：转发目标的行为完全由核心决定。

## 为什么要 Bridge

当前桌面端把核心代码随免安装包分发、在进程内直接调用 `GatewayFacade`。
MCP 版自迭代产出的修复（`hotfix/mcp-auto-*` → 合并 `main`）只进入源码仓库，
同事手上的桌面端仍然是修复前的代码。Bridge 解决的就是这一点：

```text
桌面客户端（只做交互）
        │  MCP over Streamable HTTP，Bearer 令牌
        ▼
davinci-gw-bridge（127.0.0.1:<端口>，校验令牌、转发）
        │  进程内 / STDIO / HTTP
        ▼
独立核心（唯一一份业务逻辑，可单独升级）
```

## 启动

```powershell
# 同进程核心：最简单，核心随桥接进程一起启动
python -m davinci_gw.bridge --core embedded

# 独立核心进程：核心可单独升级，桥接只做转发
python -m davinci_gw.bridge --core stdio --core-command "C:\tools\davinci-gw-mcp.exe"

# 独立核心进程（源码运行）
python -m davinci_gw.bridge --core stdio --core-command "C:\Python\python.exe -m davinci_gw.mcp"

# 内网核心服务：核心部署在另一台机器，客户端与桥接都只做客户端
python -m davinci_gw.bridge --core http --core-target http://127.0.0.1:9100/mcp --core-token <令牌>
```

常用参数：

| 参数 | 说明 |
| --- | --- |
| `--core` | `embedded` / `stdio` / `http` |
| `--core-command` | `stdio` 模式的核心完整命令行，路径含空格时用引号 |
| `--core-target` | `stdio` 模式为可执行文件路径；`http` 模式为 MCP 端点 URL |
| `--core-arg` | 追加的核心参数；参数以 `-` 开头时使用 `--core-arg=-m` 形式 |
| `--core-token` | `http` 模式访问核心所需的令牌 |
| `--host` / `--port` / `--path` | 监听地址、端口（`0` 表示系统分配）、端点路径 |
| `--token` | 桥接访问令牌；缺省时随机生成 |
| `--descriptor` | 客户端发现文件路径，缺省为 `%LOCALAPPDATA%\DaVinciGW\bridge.json` |
| `--no-descriptor` | 不写发现文件 |
| `--allow-remote` | 允许非回环监听；必须显式开启 |
| `--log-level` | 日志级别 |

安装后也可以直接使用 `davinci-gw-bridge` 命令。

## 客户端发现文件

桥接启动后写入一份 JSON，供客户端读取端口与令牌：

```json
{
  "schema_version": "1.0",
  "name": "davinci-gw-bridge",
  "version": "1.2.2",
  "pid": 1234,
  "host": "127.0.0.1",
  "port": 8765,
  "path": "/mcp",
  "url": "http://127.0.0.1:8765/mcp",
  "token": "……",
  "core": { "mode": "embedded", "target": null, "args": [] },
  "started_at": "2026-11-03T08:00:00+00:00"
}
```

文件含明文令牌，只应由当前用户可读；不需要客户端发现时可加 `--no-descriptor`。

## 对外工具

Bridge 只暴露四个网关工具，参数与语义与 MCP STDIO 服务完全一致：

| 工具 | 读写 | 说明 |
| --- | --- | --- |
| `get_gateway_capabilities` | 只读 | 核心版本、路由能力、Prepared Session 与路径安全策略；额外返回桥接端点与核心形态 |
| `validate_gateway_inputs` | 只读 | 校验 `.xlsx` 配置表与 `.arxml` 基准 |
| `preview_gateway_update` | 只读 | 预览变更并创建一次性 `preparation_id` |
| `generate_gateway_arxml` | 写 | 使用 `preparation_id` 原子生成新的 `.arxml`，禁止覆盖 |

调用顺序固定为 `validate → preview → 展示并确认 → generate`。

### 有意不暴露的工具

自动修复系列（`diagnose_generation_failure`、`start_bug_repair`、`get_bug_repair_status`、
`submit_bug_repair`、`cancel_bug_repair`）**不在桥接上开放**：

- 它们只在保留完整源码与 Git 仓库的开发机上可用（见 [MCP 本地安装与使用](MCP本地安装与使用.md)）；
- 诊断与修复工具会按客户端传入的 `repository_path`、`python_path` 启动子进程，
  放到监听端口上等于允许远程调用方驱动本机命令。

需要这些能力时，直接使用 `davinci-gw-mcp` 的 STDIO 服务。

## 安全边界

| 措施 | 说明 |
| --- | --- |
| 回环监听 | 默认只绑定 `127.0.0.1`；非回环地址必须显式 `--allow-remote`，否则拒绝启动 |
| 令牌鉴权 | 所有请求必须携带 `Authorization: Bearer <token>`；缺失或不匹配一律 401 |
| DNS 重绑定防护 | 启用 SDK 的 `TransportSecuritySettings`，校验 `Host`/`Origin` 白名单 |
| 路径安全 | 不自行解析路径；输入输出校验全部由核心执行（只接受带盘符的本地绝对路径，拒绝 UNC、设备路径与覆盖已有文件） |
| 响应上限 | 沿用核心的有界信封：错误优先、最多 200 条问题、总响应不超过 512000 字节 |
| 失败隔离 | 核心不可用时返回 `INTERNAL_FAILURE` 与 `BRIDGE_CORE_UNAVAILABLE`，不泄露异常细节与堆栈 |

令牌以 `hmac.compare_digest` 做常数时间比较。

## 客户端示例

Python（官方 MCP SDK）：

```python
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import create_mcp_http_client

http_client = create_mcp_http_client(headers={"Authorization": "Bearer <token>"})
async with Client(streamable_http_client("http://127.0.0.1:8765/mcp", http_client=http_client)) as client:
    result = await client.call_tool("get_gateway_capabilities")
```

C# 与 Electron 使用各自的官方 MCP SDK，连接同一个 Streamable HTTP 端点并携带
`Authorization` 头即可，无需了解桥接内部实现。

## 边界与限制

- **Prepared Session 属于核心进程**。`preparation_id` 在核心进程内创建并消费，
  核心重启后失效；Bridge 重启但核心不变时，客户端持有的 `preparation_id` 仍然有效。
- **Bridge 不改变会话语义**：默认 15 分钟过期、每进程最多 8 个会话、
  生成成功即消费，全部沿用核心行为。
- **端口不是必需的**。MCP 服务本身是 STDIO 传输，Bridge 是可选组件；
  不需要端口的部署可以直接使用 `davinci-gw-mcp`。
- **尚未提供发布包**。当前只提供源码运行入口；`packaging/` 下的免安装 ZIP 与
  `scripts/setup.ps1` 尚未接入 Bridge，后续按 MCP 包的既有模式补齐。
- **同机单客户端**：Bridge 面向本机桌面客户端设计，不做多租户与并发账号隔离。

## 相关文档

- [桌面前端架构改造评估报告](桌面端架构改造评估.md)：换栈与否的评估与三阶段路线
- [MCP 本地安装与使用](MCP本地安装与使用.md)：STDIO 服务的安装、诊断与自动修复
- [GUI 使用说明](GUI.md)：现有桌面端使用说明
