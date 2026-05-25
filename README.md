# 飞书日历 MCP Server

Claude Code 插件，在对话中直接增删改查飞书日历日程。

## 前置条件

1. [飞书开放平台](https://open.feishu.cn) 创建企业自建应用
2. 添加应用能力 → 开启「机器人」
3. 权限管理 → 开通 `calendar:calendar`、`calendar:calendar.event:create`、`calendar:calendar.event:read`
4. 安全设置 → 重定向 URL → 添加 `http://127.0.0.1:19999/callback`
5. 发布应用，获取 App ID 和 App Secret

## 安装

```bash
git clone <repo-url>
cd feishu-calendar-mcp
python setup.py
```

按提示输入 App ID 和 App Secret，浏览器自动打开完成飞书 OAuth 授权。重启 Claude Code 生效。

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
