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
- `BILI_ROOM_ID`（默认指向 1852633038）
- `TARGET_GIFTS`（默认监听“人气票”）
- `TARGET_MIN_NUM`（默认 50，示例场景只感谢“50 张人气票”）
- `THANK_PER_USER_DAILY`（默认 1，表示每个用户每天只感谢一次）
- 小号的 `BOT_SESSDATA / BOT_BILI_JCT / BOT_BUVID3`

> 请不要泄露 Cookie。

### 3) 运行监听 + 自动感谢
```powershell
python collector_bot.py
```

### 4) 运行检索网页
```powershell
python web_server.py
```

默认端口 `8000`：
- 浏览器打开 `http://127.0.0.1:8000`

你可以用 VS Code 的 Port Forwarding 将 8000 共享给其他人查看。

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

## 免责声明
本项目仅用于学习与技术验证，请遵守 B 站服务条款与社区规范，避免刷屏或滥用。
