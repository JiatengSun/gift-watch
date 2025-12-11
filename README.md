# gift-watch

一个最小可用的 B 站直播礼物监控 + 自动感谢 + 网页检索示例项目。

## 功能
- 监听指定直播间礼物事件（SEND_GIFT）。
- 写入本地 SQLite 数据库。
- 命中指定礼物名时，用 **小号** 自动发送感谢弹幕（需登录态）。
- 提供简单网页：按用户名/礼物名检索送礼记录。

> 该项目基于 `Nemo2011/bilibili-api`（PyPI 包名 `bilibili-api-python`）。
> B 站接口可能变化，请保持依赖版本更新。

## 环境要求（结合上游项目说明）
- Python 3.9+（上游 17.x 已移除 3.8 支持）。
- 需要自行安装一个支持异步的第三方请求库：
  - `aiohttp` / `curl_cffi` / `httpx`
  - 其中 `httpx` **不支持 WebSocket**，直播监听请选 `aiohttp` 或 `curl_cffi`。
- 所有 API 都是异步调用。

本项目默认选择 `aiohttp`，以避免部分场景下 `curl_cffi` 在直播弹幕连接时出现较高 CPU 占用的反馈。

## 快速开始

### 1) 创建环境（推荐 conda）
```powershell
conda env create -f environment.yml
conda activate gift-watch
```

或直接 pip：
```powershell
pip install -r requirements.txt
```

### 2) 配置
复制并填写 `.env`：
```powershell
copy .env.example .env
```

至少需要：
- `BILI_ROOM_ID`
- `TARGET_GIFTS`（默认监听“人气票”）
- `TARGET_GIFT_IDS`（可选，用礼物 ID 触发感谢）
- `TARGET_MIN_NUM`（默认 50，示例场景只感谢“50 张人气票”）
- `THANK_PER_USER_DAILY`（默认 1，表示每个用户每天只感谢一次）
- 小号的 `BOT_SESSDATA / BOT_BILI_JCT / BOT_BUVID3`

感谢触发条件：同一用户（按 B 站 uid）在同一天送出的目标礼物累计数量达到 `TARGET_MIN_NUM`，并且礼物名匹配 `TARGET_GIFTS` **或** 礼物 ID 匹配 `TARGET_GIFT_IDS`。
当名字和 ID 同时配置时，两组规则会各自检查，满足任意一项即触发感谢（不会要求二者同时命中）。每天每位用户满足条件后只会感谢一次（受 `THANK_PER_USER_DAILY` 影响）。

> 请不要泄露 Cookie。

### 3) 运行监听 + 自动感谢
```powershell
python collector_bot.py
```

### 4) 运行检索网页
```powershell
python web_server.py
```

默认端口 `3333`：
- 浏览器打开 `http://127.0.0.1:3333`

你可以用 VS Code 的 Port Forwarding 将 3333 共享给其他人查看。

## 目录结构
```
gift-watch/
  collector_bot.py         # 监听 + 自动感谢入口
  web_server.py            # FastAPI 入口
  config/
  core/
  db/
  services/
  web/static/index.html
```

## 常见问题
- **连不上直播/报错**
  - 优先升级 `bilibili-api-python` 到最新版。
  - 确保选择了支持 WebSocket 的请求库（`aiohttp` / `curl_cffi`）。
- **感谢弹幕被吞/触发风控**
  - 拉长 `THANK_PER_USER_COOLDOWN_SEC`。
  - 避免小号进行高频自动聊天，仅做礼物感谢。
- **浏览器访问 404（显示 nginx/1.18.0）**
  - 多数情况下是系统/浏览器代理把 `http://127.0.0.1:3333` 转发到了外部代理服务器。
  - 关闭代理：Windows 设置 → 网络和 Internet → 代理 → 关闭“使用代理服务器”。
  - 如果设备强制配置了 WinHTTP 代理，可在提升权限的 PowerShell 中检查/重置：
    - 查看：`netsh winhttp show proxy`
    - 清除：`netsh winhttp reset proxy`（需要以管理员身份运行；若显示“拒绝访问”，请切换管理员终端或联系 IT）
  - 为本地地址添加直连规则（重新打开终端生效）：
    - `setx NO_PROXY "127.0.0.1,localhost"`
    - `setx no_proxy "127.0.0.1,localhost"`
  - 诊断：在 PowerShell 运行 `curl http://127.0.0.1:3333 --noproxy "*"` 应返回网页源代码；若仍显示 nginx，说明代理未关闭成功。
  - 代理关闭后再用浏览器访问，即可命中本地 Uvicorn 服务，而不是外部 nginx。

## 免责声明
本项目仅用于学习与技术验证，请遵守 B 站服务条款与社区规范，避免刷屏或滥用。
