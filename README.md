# 飞书日历 MCP Server

Claude Code 插件，在对话中直接增删改查飞书日历日程。

## 前置条件

1. [飞书开放平台](https://open.feishu.cn) 创建企业自建应用
2. 添加应用能力 → 开启「机器人」
3. 权限管理 → 开通 `calendar:calendar`、`calendar:calendar.event:create`、`calendar:calendar.event:read`
4. 安全设置 → 重定向 URL → 添加 `http://127.0.0.1:19999/callback`
5. 发布应用，获取 App ID 和 App Secret

## 安装

建议统一放置路径，方便跨设备管理：

```bash
mkdir -p ~/projects                                    # 没有 projects 目录就先创建
cd ~/projects
git clone https://github.com/Sugarcgmade/feishu-calendar-mcp.git
cd feishu-calendar-mcp
python setup.py                                         # 输入 App ID / Secret → 浏览器 OAuth → 自动配置完成
```

按提示输入 App ID 和 App Secret，浏览器自动打开完成飞书 OAuth 授权。重启 Claude Code 生效。

## 架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         你的电脑                                 │
│                                                                  │
│  ┌──────────┐    自然语言     ┌──────────────┐                   │
│  │   你     │ ◄────────────► │  Claude Code │                    │
│  │ (用户)   │                │  claude.exe   │                   │
│  └──────────┘                └──────┬───────┘                   │
│                                     │                            │
│                              读取    │  spawn 子进程              │
│                          ~/.claude/ │  stdio JSON-RPC (MCP)     │
│                      ┌──────────────┼──────────────┐            │
│                      ▼              ▼              ▼            │
│               ┌──────────┐  ┌──────────────┐  ┌──────────┐     │
│               │ CLAUDE.md │  │  .mcp.json   │  │  其他    │     │
│               │ (行为规则) │  │ {feishu-     │  │  MCP     │     │
│               │           │  │  calendar:   │  │ Server   │     │
│               │           │  │  python      │  │          │     │
│               │           │  │  ~/projects/ │  │          │     │
│               │           │  │  feishu-     │  │          │     │
│               │           │  │  calendar-   │  │          │     │
│               │           │  │  mcp/        │  │          │     │
│               │           │  │  server.py}  │  │          │     │
│               └──────────┘  └──────┬───────┘  └──────────┘     │
│                                    │                             │
│                          ┌─────────▼──────────┐                 │
│                          │  feishu-calendar   │                 │
│                          │  MCP Server        │                 │
│                          │  ~/projects/       │                 │
│                          │  feishu-calendar-  │                 │
│                          │  mcp/server.py      │                 │
│                          │                    │                 │
│                          │  Tools:            │                 │
│                          │  · event_query     │                 │
│                          │  · event_create    │                 │
│                          │  · event_update    │                 │
│                          │  · event_delete     │                 │
│                          │  · calendar_info   │                 │
│                          └────────┬───────────┘                 │
│                                   │                              │
│                          user_access_token (OAuth)              │
│                          token.json (自动刷新)                   │
│                                   │                              │
└───────────────────────────────────┼──────────────────────────────┘
                                    │ HTTPS
                                    ▼
                    ┌───────────────────────────┐
                    │     飞书开放平台           │
                    │     open.feishu.cn         │
                    │                            │
                    │  Calendar V4 API           │
                    │  · /calendars/primary/     │
                    │    events                  │
                    │                            │
                    │  Auth                      │
                    │  · OAuth authorize         │
                    │  · refresh_access_token    │
                    └───────────────────────────┘
```

## 使用

```
明天下午3点会议室开会，加上日程
查一下今天有什么安排
把刚才那个日程改到4点
删掉那个日程
```

## 文件结构

```
feishu-calendar-mcp/
├── server.py          # MCP Server（操作你的个人日历）
├── setup.py           # 一键安装脚本（OAuth + 配置写入）
├── requirements.txt   # mcp, httpx
├── token.json         # OAuth token（自动生成，不进 git）
└── README.md
```
