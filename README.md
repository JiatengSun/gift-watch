# gift-watch

一个最小可用的 B 站直播礼物监控 + 自动感谢 + 网页检索示例项目。

## 功能
- 监听指定直播间礼物事件（SEND_GIFT）。
- 写入本地 SQLite 数据库。
- 命中指定礼物名时，用 **小号** 自动发送感谢弹幕（需登录态）。
- 提供简单网页：按用户名/礼物名检索送礼记录。
- 在弹幕中输入短句（默认“查询盲盒”或“查询心动盲盒盈亏”）可查询心动盲盒投入与开出礼物价值的盈亏，并自动回复弹幕（盲盒基础礼物不入库，按开出礼物数量×¥15 计算投入，开出的礼物按实际金额计算）。

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
- `THANK_GUARD`（默认 0，设置为 1 时对大航海 GUARD_BUY 发送“感谢xxx的yy！！你最帅了！”弹幕）
- 小号的 `BOT_SESSDATA / BOT_BILI_JCT / BOT_BUVID3`
- `DANMAKU_MAX_LENGTH`：弹幕最大长度（默认 20，超长时会自动截断并重发，避免接口报 1003212 超长错误）。
- `DANMAKU_QUEUE_ENABLED`：是否启用持久化弹幕队列（默认 1），多实例/多端口可共用同一队列。
- `DANMAKU_QUEUE_INTERVAL_SEC`：全局弹幕发送间隔（默认 3s）。
- `DANMAKU_QUEUE_DB_PATH`：队列数据库路径（默认与 `DB_PATH` 相同）。
- `RAW_EVENT_STORAGE_MODE`：事件原始载荷存储模式，支持 `full` / `compact` / `none`，默认 `compact`。`compact` 会只保留兼容分析所需的精简 JSON，显著降低数据库增长速度。
- `COMPACT_LEGACY_PAYLOADS_ON_STARTUP`：是否在启动时自动把历史 `raw_json` 瘦身并执行一次 `VACUUM`，默认 `1`。首次升级后启动可能会慢一些，但完成后数据库体积会下降，且老数据无需清库。

盲盒盈亏查询可在控制台配置，也可以按需调整以下环境变量：
- `BLIND_BOX_ENABLED`：是否开启弹幕查询（默认 1）。
- `BLIND_BOX_TRIGGERS`：触发短句，逗号或换行分隔，默认包含 `查询盲盒` 与 `查询心动盲盒盈亏`。
- `BLIND_BOX_BASE_GIFT`：盲盒基础礼物名，默认 `心动盲盒`。
- `BLIND_BOX_REWARDS`：盲盒可能开出的礼物名列表，默认包含电影票/棉花糖/爱心抱枕等；留空时会按除基础礼物外的全部已入库礼物统计产出。
- `BLIND_BOX_TEMPLATE`：弹幕回复模板，支持 {uname} / {base_cost_yuan} / {reward_value_yuan} / {profit_yuan} 等占位符。
- `BLIND_BOX_SEND_DANMAKU`：是否发送盈亏弹幕（默认 1，可关闭仅记录日志）。
- 启动时会抓取礼物列表并填充 `GIFT_PRICE_CACHE` 环境变量，礼物价格以金瓜子计（1000:1 折算人民币），播报/统计会按礼物真实金额计算。
- 盲盒的基础礼物不会入库也不会计入流水，盲盒开出的礼物会正常入库并计入流水，盈亏统计按“开出礼物数量×¥15”作为投入、礼物本身金额作为产出（若未配置奖励礼物列表，则按全部非基础礼物的金额计算产出）。

感谢触发条件：同一用户（按 B 站 uid）在同一天送出的目标礼物累计数量达到 `TARGET_MIN_NUM`，并且礼物名匹配 `TARGET_GIFTS` **或** 礼物 ID 匹配 `TARGET_GIFT_IDS`。
当名字和 ID 同时配置时，两组规则会各自检查，满足任意一项即触发感谢（不会要求二者同时命中）。每天每位用户满足条件后只会感谢一次（受 `THANK_PER_USER_DAILY` 影响）。

> 请不要泄露 Cookie。

### 3) 运行监听 + 自动感谢
可指定独立的 `.env`，方便多实例运行：
```powershell
python collector_bot.py --env-file .env.room1
```

### 4) 运行检索网页
可以直接跑内置脚本：
```powershell
python web_server.py
```

或者用 Uvicorn CLI 指定端口、Host 与环境文件（多实例/多端口场景）：
```powershell
uvicorn web.app:app --host 0.0.0.0 --port 5555 --env-file .env-xsz
```

默认端口 `3333`：
- 浏览器打开 `http://127.0.0.1:3333`

前端会在所有 API 请求上追加 `?env=...`，与填写的 `.env` 路径绑定，后端会按对应配置加载数据库与房间。

你可以用 VS Code 的 Port Forwarding 将 3333 共享给其他人查看；如果用自定义端口（如上例的 5555），按对应端口转发即可。

### 5) 访问密码门户（给多个主播共用一个入口）

如果你不想公开列出主播名单，可以启用统一密码入口：

- 公开入口：`/gift-watch/access`
- 主播输入各自密码后进入自己的页面
- 管理员输入管理员密码后进入 `/gift-watch/manager`

配置方式：

1. 在公共 Web 实例使用的环境变量里设置：
```env
MANAGER_PORTAL_PASSWORD=你自己的管理员密码
ACCESS_COOKIE_SECRET=尽量长的随机字符串
```

2. 在每个主播对应的 `.env-*` 文件里设置：
```env
PORTAL_PASSWORD=该主播的专属密码
```

注意：

- 每个 `PORTAL_PASSWORD` 必须唯一，不能重复
- 公开主页只需要把入口指向 `/gift-watch/access`
- 主播登录后只会看到自己绑定的 `.env-*` 数据；管理员密码会进入管理页

### 6) 统一 Web 门户启动（推荐 Ubuntu）

如果你想放弃“每个主播一个网页端口”的模式，只保留一个统一入口，推荐只启动一个 Web 门户实例，例如 `9999`：

```bash
cd /home/tencentCloud/gift-watch
bash ./scripts/start_web_portal.sh .env-lqx 9999
```

然后访问：

```text
http://你的公网IP:9999/gift-watch/access
```

停止：

```bash
cd /home/tencentCloud/gift-watch
bash ./scripts/stop_web_portal.sh .env-lqx 9999
```

说明：

- 这个统一入口实例会读取所有 `.env-*` 里的 `PORTAL_PASSWORD`
- 主播输入自己的密码后，会在同一个 Web 门户里看到自己绑定的数据
- 你只需要保留一个对外开放的 Web 端口，例如 `9999`
- 如果前面挂了 `nginx`，建议把外部路径统一代理到 `/gift-watch/*`

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
