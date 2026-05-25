"""
飞书日历 MCP Server 一键安装脚本
用法: python setup.py
"""

import json
import os
import secrets
import sys
import threading
import time
import urllib.parse
import webbrowser
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

# ── 配置 ────────────────────────────────────────────

APP_ID = input("飞书 App ID: ").strip()
APP_SECRET = input("飞书 App Secret: ").strip()

if not APP_ID or not APP_SECRET:
    print("App ID / Secret 不能为空")
    sys.exit(1)

# ── 检查依赖 ────────────────────────────────────────

try:
    import httpx
except ImportError:
    print("正在安装 httpx...")
    os.system(f"{sys.executable} -m pip install httpx mcp -q")

# ── 确定安装位置 ────────────────────────────────────

INSTALL_DIR = Path(__file__).parent.resolve()
CLAUDE_DIR = Path.home() / ".claude"
MCP_JSON = CLAUDE_DIR / ".mcp.json"
TOKEN_FILE = INSTALL_DIR / "token.json"

print(f"安装目录: {INSTALL_DIR}")

# ── 启动回调服务器 ──────────────────────────────────

result = {}

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        code = params.get("code", [None])[0]
        if code:
            result["code"] = code
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("<h2>授权成功</h2><p>可以关闭页面</p>".encode("utf-8"))
        else:
            self.send_response(400)
            self.end_headers()
    def log_message(self, *args): pass

server = HTTPServer(("127.0.0.1", 19999), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()

# ── OAuth 授权 ──────────────────────────────────────

scope = "calendar:calendar calendar:calendar.event:create calendar:calendar.event:read"
state = secrets.token_urlsafe(16)
url = (
    f"https://open.feishu.cn/open-apis/authen/v1/authorize"
    f"?app_id={APP_ID}"
    f"&redirect_uri={urllib.parse.quote('http://127.0.0.1:19999/callback', safe='')}"
    f"&state={state}"
    f"&scope={urllib.parse.quote(scope, safe='')}"
)

print()
print("请在浏览器中完成飞书 OAuth 授权：")
print(url)
print()
webbrowser.open(url)

for _ in range(60):
    if result.get("code"):
        break
    time.sleep(2)
server.shutdown()

code = result.get("code")
if not code:
    print("超时，请重新运行")
    sys.exit(1)

# ── 换取 token ──────────────────────────────────────

import asyncio

async def exchange():
    import httpx
    client = httpx.AsyncClient(timeout=30)

    r = await client.post(
        "https://open.feishu.cn/open-apis/auth/v3/app_access_token/internal",
        json={"app_id": APP_ID, "app_secret": APP_SECRET},
    )
    app_token = r.json()["app_access_token"]

    r = await client.post(
        "https://open.feishu.cn/open-apis/authen/v1/oidc/access_token",
        json={"grant_type": "authorization_code", "code": code},
        headers={"Authorization": f"Bearer {app_token}", "Content-Type": "application/json"},
    )
    data = r.json()
    if data.get("code") != 0:
        print(f"换取 token 失败: {data}")
        return False

    uat = data["data"]["access_token"]
    rt = data["data"]["refresh_token"]

    # 保存 token
    TOKEN_FILE.write_text(
        json.dumps({"user_access_token": uat, "refresh_token": rt}, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Token 已保存到 {TOKEN_FILE}")

    # 测试：创建一个测试日程
    cst = timezone(timedelta(hours=8))
    now = datetime.now(cst) + timedelta(hours=1)
    start_ts = str(int(now.timestamp()))
    end_ts = str(int((now + timedelta(hours=1)).timestamp()))

    r = await client.post(
        "https://open.feishu.cn/open-apis/calendar/v4/calendars/primary/events",
        headers={"Authorization": f"Bearer {uat}", "Content-Type": "application/json"},
        json={
            "summary": "安装成功 - 飞书日历 MCP Server",
            "start_time": {"timestamp": start_ts},
            "end_time": {"timestamp": end_ts},
        },
    )
    if r.json().get("code") == 0:
        print("测试日程已创建，打开飞书确认")
    else:
        print(f"测试日程创建失败: {r.json()}")

    await client.aclose()
    return True

ok = asyncio.run(exchange())
if not ok:
    sys.exit(1)

# ── 写入 .mcp.json ──────────────────────────────────

server_path = str(INSTALL_DIR / "server.py").replace("\\", "\\\\")
mcp_config = {
    "mcpServers": {
        "feishu-calendar": {
            "command": sys.executable,
            "args": [server_path],
            "env": {
                "FEISHU_APP_ID": APP_ID,
                "FEISHU_APP_SECRET": APP_SECRET,
            },
        }
    }
}

existing = {}
if MCP_JSON.exists():
    existing = json.loads(MCP_JSON.read_text(encoding="utf-8"))

# 合并，不覆盖已有的其他 MCP server
if "mcpServers" not in existing:
    existing["mcpServers"] = {}
existing["mcpServers"].update(mcp_config["mcpServers"])

MCP_JSON.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"MCP 配置已写入 {MCP_JSON}")

print()
print("=" * 50)
print("安装完成！重启 Claude Code 即可使用。")
print()
print("使用方法（在任意 Claude Code 对话中）：")
print("  明天下午3点会议室开会，加上日程")
print("  查一下今天有什么安排")
print("  把刚才那个日程改到4点")
print("=" * 50)
