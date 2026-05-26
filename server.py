"""
飞书日历 MCP Server
在 Claude Code 中直接操作飞书日历：查询、创建、修改、删除日程
"""

import os
import sys
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx
from mcp.server.fastmcp import FastMCP

FEISHU_BASE = "https://open.feishu.cn/open-apis"
TZ_SHANGHAI = timezone(timedelta(hours=8))
TOKEN_FILE = Path(__file__).parent / "token.json"

APP_ID = os.getenv("FEISHU_APP_ID", "")
APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")

# user_access_token 过期 / 无效的错误码
_TOKEN_ERROR_CODES = (99991663, 99991664, 99991677, 99991668)

_token_cache: dict | None = None
_http: httpx.AsyncClient | None = None


def parse_iso_to_ts(s: str) -> str:
    s = s.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        dt = datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=TZ_SHANGHAI)
    return str(int(dt.timestamp()))


def ts_to_display(ts: str) -> str:
    try:
        return datetime.fromtimestamp(int(ts), tz=TZ_SHANGHAI).strftime("%Y-%m-%d %H:%M")
    except (ValueError, OSError):
        return ts


def fmt_event(e: dict) -> dict:
    loc = e.get("location") or {}
    loc_name = loc.get("name", "") if isinstance(loc, dict) else str(loc)
    st = e.get("start_time", {}) or {}
    et = e.get("end_time", {}) or {}
    start = st.get("date_time") or st.get("timestamp", "")
    end = et.get("date_time") or et.get("timestamp", "")
    return {
        "event_id": e.get("event_id"),
        "summary": e.get("summary", ""),
        "start": ts_to_display(start) if start else "",
        "end": ts_to_display(end) if end else "",
        "location": loc_name,
        "description": e.get("description", ""),
        "status": e.get("status", ""),
    }


async def get_client() -> httpx.AsyncClient:
    global _http
    if _http is None:
        _http = httpx.AsyncClient(timeout=30)
    return _http


# ── 用户 Token 管理 ──────────────────────────────────

async def _load_tokens() -> dict:
    global _token_cache
    if _token_cache is not None:
        return _token_cache

    if TOKEN_FILE.exists():
        _token_cache = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
        return _token_cache
    return {}


async def _save_tokens(data: dict) -> None:
    global _token_cache
    data["updated_at"] = int(datetime.now(TZ_SHANGHAI).timestamp())
    _token_cache = data
    TOKEN_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


async def _refresh_user_token(refresh_token: str) -> tuple[str, str] | None:
    """用 refresh_token 换取新的 (user_access_token, refresh_token)

    返回 (access_token, refresh_token) 或 None。
    飞书每次 refresh 都会下发新的 refresh_token，旧的即失效，必须同时保存。
    """
    client = await get_client()
    resp = await client.post(
        f"{FEISHU_BASE}/authen/v1/refresh_access_token",
        json={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "app_id": APP_ID,
            "app_secret": APP_SECRET,
        },
    )
    data = resp.json()
    if data.get("code") != 0:
        return None
    d = data["data"]
    return d["access_token"], d.get("refresh_token", refresh_token)


async def get_token() -> str:
    """获取有效的 user_access_token，快过期时主动续期"""
    tokens = await _load_tokens()
    uat = tokens.get("user_access_token", "")

    if not uat:
        raise RuntimeError(
            "缺少飞书授权。请运行 OAuth 授权流程获取 user_access_token。"
        )

    # user_access_token 有效期 2 小时，提前 300 秒主动刷新
    updated_at = tokens.get("updated_at", 0)
    age = int(datetime.now(TZ_SHANGHAI).timestamp()) - updated_at
    if age > 6900:
        rt = tokens.get("refresh_token", "")
        if rt:
            result = await _refresh_user_token(rt)
            if result:
                new_uat, new_rt = result
                tokens["user_access_token"] = new_uat
                tokens["refresh_token"] = new_rt
                await _save_tokens(tokens)
                return new_uat

    return uat


async def refresh_token_if_needed(error_code: int) -> str | None:
    """API 返回 token 过期时自动刷新，同时保存新的 refresh_token"""
    if error_code not in _TOKEN_ERROR_CODES:
        return None

    tokens = await _load_tokens()
    rt = tokens.get("refresh_token", "")
    if not rt:
        return None

    result = await _refresh_user_token(rt)
    if result:
        new_uat, new_rt = result
        tokens["user_access_token"] = new_uat
        tokens["refresh_token"] = new_rt
        await _save_tokens(tokens)
        return new_uat
    return None


async def _call_api(method: str, path: str, **kwargs) -> dict:
    token = await get_token()
    client = await get_client()
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {token}"
    resp = await client.request(method, f"{FEISHU_BASE}{path}", headers=headers, **kwargs)
    data = resp.json()

    # token 过期/无效，尝试刷新后重试一次
    if data.get("code") in _TOKEN_ERROR_CODES:
        new_token = await refresh_token_if_needed(data["code"])
        if new_token:
            headers["Authorization"] = f"Bearer {new_token}"
            resp = await client.request(method, f"{FEISHU_BASE}{path}", headers=headers, **kwargs)
            data = resp.json()

    return data


# ── MCP Server ────────────────────────────────────────

mcp = FastMCP("feishu-calendar")


@mcp.tool()
async def feishu_event_query(
    start_date: str = "",
    end_date: str = "",
    keyword: str = "",
) -> str:
    """查询我的飞书个人日程，可按日期范围和关键词筛选。

    start_date / end_date 格式：YYYY-MM-DD，例如 "2026-05-25"。
    若都不给，默认查今天。keyword 匹配日程标题和描述。
    """
    today = datetime.now(TZ_SHANGHAI).strftime("%Y-%m-%d")
    start = start_date or today
    end = end_date or start

    start_ts = str(int(datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=TZ_SHANGHAI).timestamp()))
    end_ts = str(int(datetime.strptime(end, "%Y-%m-%d").replace(tzinfo=TZ_SHANGHAI, hour=23, minute=59, second=59).timestamp()))

    data = await _call_api(
        "GET",
        "/calendar/v4/calendars/primary/events",
        params={"start_time": start_ts, "end_time": end_ts, "page_size": 500},
    )

    if data.get("code") != 0:
        return f"查询失败: {data.get('msg', data)}"

    items = data.get("data", {}).get("items", [])

    if keyword:
        kw = keyword.lower()
        items = [
            e for e in items
            if kw in (e.get("summary", "") + (e.get("description") or "")).lower()
        ]

    if not items:
        scope = f"{start} ~ {end}"
        hint = f"（关键词: {keyword}）" if keyword else ""
        return f"{scope} 没有找到日程{hint}"

    lines = [f"{start} ~ {end} 共 {len(items)} 个日程:"]
    for e in items:
        f = fmt_event(e)
        loc = f" @{f['location']}" if f["location"] else ""
        cancelled = " [已取消]" if f["status"] == "cancelled" else ""
        lines.append(
            f"  [{f['event_id']}] {f['start']} -> {f['end']}"
            f"  {f['summary']}{loc}{cancelled}"
        )
    return "\n".join(lines)


@mcp.tool()
async def feishu_event_create(
    summary: str,
    start_time: str,
    end_time: str,
    location: str = "",
    description: str = "",
) -> str:
    """在我的飞书个人日历中创建日程。

    summary: 日程标题
    start_time / end_time: ISO 8601 格式，如 "2026-05-25T14:00:00+08:00"
    location: 地点（可选）
    description: 描述（可选）
    """
    return await _upsert_event(None, summary, start_time, end_time, location, description)


@mcp.tool()
async def feishu_event_update(
    event_id: str,
    summary: str = "",
    start_time: str = "",
    end_time: str = "",
    location: str = "",
    description: str = "",
) -> str:
    """修改我的飞书个人日历中的日程。event_id 必填，其余字段只更新传入的非空值。

    先通过 feishu_event_query 获取 event_id。
    """
    return await _upsert_event(event_id, summary, start_time, end_time, location, description)


async def _upsert_event(
    event_id: str | None,
    summary: str,
    start_time: str,
    end_time: str,
    location: str,
    description: str,
) -> str:
    body = {}
    if summary:
        body["summary"] = summary
    if start_time:
        body["start_time"] = {"timestamp": parse_iso_to_ts(start_time)}
    if end_time:
        body["end_time"] = {"timestamp": parse_iso_to_ts(end_time)}
    if location:
        body["location"] = {"name": location}
    if description:
        body["description"] = description

    if event_id:
        if not body:
            return "错误: 至少需要一个要更新的字段"
        data = await _call_api(
            "PATCH", f"/calendar/v4/calendars/primary/events/{event_id}", json=body
        )
        action = "更新"
    else:
        if not summary or not start_time or not end_time:
            return "错误: 创建日程需要 summary, start_time, end_time"
        data = await _call_api(
            "POST", "/calendar/v4/calendars/primary/events", json=body
        )
        action = "创建"

    if data.get("code") != 0:
        return f"{action}失败: {data.get('msg', data)}"

    e = fmt_event(data.get("data", {}).get("event", {}))
    loc = f" @{e['location']}" if e["location"] else ""
    return f"已{action}日程: [{e['event_id']}] {e['summary']} | {e['start']} -> {e['end']}{loc}"


@mcp.tool()
async def feishu_event_delete(event_id: str) -> str:
    """删除我的飞书个人日历中的日程。先通过 feishu_event_query 获取 event_id 后再调用。

    注意: 删除操作不可撤销。
    """
    data = await _call_api(
        "DELETE", f"/calendar/v4/calendars/primary/events/{event_id}"
    )
    if data.get("code") != 0:
        return f"删除失败: {data.get('msg', data)}"
    return f"已删除日程 {event_id}"


@mcp.tool()
async def feishu_calendar_info() -> str:
    """查看飞书日历连接状态。"""
    tokens = await _load_tokens()
    if tokens.get("user_access_token"):
        return "已连接你的飞书个人日历，所有日程操作直接面对你的个人日历。"
    return "未授权，请先完成飞书 OAuth 授权。"


if __name__ == "__main__":
    if not APP_ID or not APP_SECRET:
        print("错误: 请设置 FEISHU_APP_ID 和 FEISHU_APP_SECRET 环境变量", file=sys.stderr)
        sys.exit(1)
    mcp.run()
