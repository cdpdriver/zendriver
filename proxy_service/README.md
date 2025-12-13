# Zendriver Proxy Service 使用说明

## 项目简介

Zendriver Proxy Service 是一个基于 FastAPI 的浏览器代理服务，提供高性能的网页抓取能力。支持多并发、代理管理、Cookie 管理、Cloudflare 验证自动处理等功能。

### 主要特性

- ✅ **多并发支持** - 支持配置最大并发数，自动管理浏览器实例池
- ✅ **代理支持** - 支持 HTTP/HTTPS/SOCKS5 代理，包含认证功能
- ✅ **Cookie 管理** - 按域名和代理隔离存储，自动复用
- ✅ **Cloudflare 验证** - 自动检测并处理 Cloudflare 挑战
- ✅ **元素等待** - 支持等待指定 CSS 选择器元素出现
- ✅ **超时控制** - 可配置的请求超时时间
- ✅ **页面状态检测** - 自动检测被阻止、队列等待、无法访问等状态

## 安装

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 确保已安装 Zendriver

该服务依赖 `zendriver` 库，请确保已正确安装：

```bash
pip install zendriver
```

### 3. 服务器环境：安装虚拟显示（可选）

如果**在服务器上不使用无头模式**（`HEADLESS = False`），需要安装虚拟显示服务器 Xvfb，用于绕过浏览器的 headless 检测。

#### 安装 Xvfb

```bash
# Ubuntu/Debian
sudo apt install xvfb

# CentOS/RHEL
sudo yum install xorg-x11-server-Xvfb
```

#### 启动虚拟显示

```bash
# 启动 Xvfb 虚拟显示（显示编号 :99，分辨率 1920x1080，24位色深）
Xvfb :99 -screen 0 1920x1080x24 -nolisten tcp -ac > /dev/null 2>&1 &

# 设置 DISPLAY 环境变量
export DISPLAY=:99
```

#### 检查虚拟显示状态

```bash
# 检查 Xvfb 是否运行
pgrep -u "$USER" -x Xvfb
```

#### 停止虚拟显示

```bash
# 停止 Xvfb
pkill -u "$USER" Xvfb && echo "Xvfb 已停止" || echo "Xvfb 未运行"
```

#### 在启动脚本中自动设置

如果使用 systemd 或启动脚本，可以在服务启动前设置 DISPLAY 环境变量：

**systemd 服务文件示例**：

```ini
[Unit]
Description=Zendriver Proxy Service
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/home/spider/zendriver
Environment="DISPLAY=:99"
ExecStartPre=/usr/bin/Xvfb :99 -screen 0 1920x1080x24 -nolisten tcp -ac
ExecStart=/usr/bin/python3 -m uvicorn proxy_service.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**启动脚本示例**：

```bash
#!/bin/bash
# 启动虚拟显示
Xvfb :99 -screen 0 1920x1080x24 -nolisten tcp -ac > /dev/null 2>&1 &
export DISPLAY=:99

# 启动服务
uvicorn proxy_service.main:app --host 0.0.0.0 --port 8000
```

**注意**：
- 如果使用无头模式（`HEADLESS = True`），则不需要安装 Xvfb
- 虚拟显示主要用于绕过某些网站对 headless 浏览器的检测
- 生产环境建议使用无头模式以节省资源

## 启动服务

### 方式一：使用 uvicorn 启动（前台）

```bash
uvicorn proxy_service.main:app --host 0.0.0.0 --port 8000
```

**注意**：这是前台启动，会占用当前终端窗口。按 `Ctrl+C` 可停止服务。

### 方式二：后台启动

#### 使用 nohup（推荐）

```bash
nohup uvicorn proxy_service.main:app --host 0.0.0.0 --port 8000 > proxy_service.log 2>&1 &
```

- 日志输出到 `proxy_service.log` 文件
- 使用 `tail -f proxy_service.log` 查看实时日志
- 使用 `ps aux | grep uvicorn` 查找进程
- 使用 `kill <PID>` 停止服务

#### 使用 screen（适合开发调试）

```bash
# 创建新的 screen 会话
screen -S proxy_service

# 在 screen 中启动服务
uvicorn proxy_service.main:app --host 0.0.0.0 --port 8000

# 按 Ctrl+A 然后按 D 分离会话
# 重新连接：screen -r proxy_service
```

#### 使用 systemd（生产环境推荐）

创建服务文件 `/etc/systemd/system/proxy-service.service`：

```ini
[Unit]
Description=Zendriver Proxy Service
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/home/spider/zendriver
ExecStart=/usr/bin/python3 -m uvicorn proxy_service.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

然后使用 systemctl 管理：

```bash
# 启动服务
sudo systemctl start proxy-service

# 停止服务
sudo systemctl stop proxy-service

# 查看状态
sudo systemctl status proxy-service

# 查看日志
sudo journalctl -u proxy-service -f

# 开机自启
sudo systemctl enable proxy-service
```

### 方式三：直接运行

```bash
python -m proxy_service.main
```

### 方式四：使用 Python 脚本

```bash
python proxy_service/main.py
```

服务启动后，默认监听在 `http://0.0.0.0:8000`

## 配置

在 `main.py` 中可以修改以下配置：

```python
MAX_CONCURRENT = 5      # 最大并发数
DEFAULT_TIMEOUT = 30    # 默认超时时间（秒）
HEADLESS = False        # 是否使用无头模式
```

### 配置说明

- **MAX_CONCURRENT**: 最大并发请求数，根据服务器性能调整
- **DEFAULT_TIMEOUT**: 默认请求超时时间（秒）
- **HEADLESS**: 
  - `True` - 无头模式，不显示浏览器窗口，适合生产环境
  - `False` - 有界面模式，需要显示服务器支持
    - 本地开发：直接使用
    - 服务器环境：需要安装并启动 Xvfb 虚拟显示（见上方安装说明）

## API 文档

服务启动后，可以访问以下地址查看自动生成的 API 文档：

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## API 端点

### 1. 抓取页面 - `POST /fetch`

抓取指定 URL 的页面 HTML 内容。

#### 请求参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `url` | string | 是 | 目标 URL |
| `wait_for` | string | 否 | 等待的 CSS 选择器（如 `#main-content`） |
| `timeout` | float | 否 | 超时时间（秒），默认 30 |
| `proxy` | string | 否 | 代理 URL，格式见下方 |
| `cloudflare` | object | 否 | Cloudflare 验证配置 |

#### 代理 URL 格式

支持以下格式：

- `http://host:port` - HTTP 代理
- `http://user:pass@host:port` - 带认证的 HTTP 代理
- `socks5://host:port` - SOCKS5 代理
- `socks5://user:pass@host:port` - 带认证的 SOCKS5 代理

#### Cloudflare 配置

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | boolean | `true` | 是否启用 CF 验证 |
| `max_retries` | integer | `3` | 最大重试次数 |
| `click_delay` | float | `2.0` | 点击间隔（秒） |
| `challenge_timeout` | float | `15.0` | 验证超时（秒） |

#### 请求示例

```bash
curl -X POST "http://localhost:8000/fetch" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com",
    "wait_for": "#main-content",
    "timeout": 20,
    "proxy": "http://user:pass@proxy.example.com:8080",
    "cloudflare": {
      "enabled": true,
      "max_retries": 3,
      "click_delay": 2.0,
      "challenge_timeout": 15.0
    }
  }'
```

#### 响应示例

```json
{
  "success": true,
  "html": "<!DOCTYPE html>...",
  "url": "https://example.com",
  "elapsed": 2.345,
  "status": "ok",
  "cloudflare": {
    "detected": true,
    "solved": true,
    "retries": 1
  }
}
```

#### 响应字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `success` | boolean | 是否成功 |
| `html` | string | 页面 HTML 内容 |
| `url` | string | 最终 URL（可能有重定向） |
| `elapsed` | float | 耗时（秒） |
| `error` | string | 错误信息（失败时） |
| `status` | string | 页面状态：`ok`/`blocked`/`queue`/`unreachable` |
| `cloudflare` | object | Cloudflare 状态信息 |

### 2. 获取服务状态 - `GET /status`

获取服务的运行状态和统计信息。

#### 请求示例

```bash
curl "http://localhost:8000/status"
```

#### 响应示例

```json
{
  "status": "running",
  "max_concurrent": 5,
  "headless": false,
  "browsers": [
    {
      "proxy": null,
      "tabs": 2
    },
    {
      "proxy": "http://proxy.example.com:8080",
      "tabs": 1
    }
  ],
  "cookie_keys": [
    {
      "domain": "example.com",
      "proxy": null
    },
    {
      "domain": "example.com",
      "proxy": "http://proxy.example.com:8080"
    }
  ]
}
```

### 3. 获取 Cookies - `GET /cookies`

获取指定域名和代理的 Cookies。

#### 请求参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `domain` | string | 是 | 域名或 URL（如 `example.com` 或 `https://example.com/path`） |
| `proxy` | string | 否 | 代理服务器地址（如 `http://proxy:8080`） |

#### 请求示例

```bash
curl "http://localhost:8000/cookies?domain=example.com&proxy=http://proxy.example.com:8080"
```

#### 响应示例

```json
{
  "domain": "example.com",
  "proxy": "http://proxy.example.com:8080",
  "cookies": [
    {
      "name": "session_id",
      "value": "abc123",
      "domain": ".example.com",
      "path": "/",
      "secure": true,
      "http_only": true,
      "expires": 1234567890
    }
  ]
}
```

### 4. 清除 Cookies - `DELETE /cookies`

清除指定域名和代理的 Cookies。

#### 请求参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `domain` | string | 否 | 指定域名或 URL，不传则清除所有 |
| `proxy` | string | 否 | 指定代理，不传则清除该域名的所有代理 |

#### 请求示例

```bash
# 清除指定域名和代理的 Cookies
curl -X DELETE "http://localhost:8000/cookies?domain=example.com&proxy=http://proxy.example.com:8080"

# 清除指定域名的所有 Cookies
curl -X DELETE "http://localhost:8000/cookies?domain=example.com"

# 清除所有 Cookies
curl -X DELETE "http://localhost:8000/cookies"
```

#### 响应示例

```json
{
  "message": "Cookies cleared for example.com (proxy: http://proxy.example.com:8080)"
}
```

### 5. 健康检查 - `GET /health`

检查服务是否正常运行。

#### 请求示例

```bash
curl "http://localhost:8000/health"
```

#### 响应示例

```json
{
  "status": "ok"
}
```

## 使用示例

### Python 示例

```python
import requests

# 基础抓取
response = requests.post(
    "http://localhost:8000/fetch",
    json={
        "url": "https://example.com",
        "wait_for": "#main-content",
        "timeout": 20
    }
)
result = response.json()
print(f"Success: {result['success']}")
print(f"HTML length: {len(result['html'])}")

# 使用代理抓取
response = requests.post(
    "http://localhost:8000/fetch",
    json={
        "url": "https://example.com",
        "proxy": "http://user:pass@proxy.example.com:8080",
        "cloudflare": {
            "enabled": True,
            "max_retries": 3
        }
    }
)
result = response.json()

# 获取 Cookies
response = requests.get(
    "http://localhost:8000/cookies",
    params={
        "domain": "example.com",
        "proxy": "http://proxy.example.com:8080"
    }
)
cookies = response.json()["cookies"]
print(f"Found {len(cookies)} cookies")
```

### JavaScript/Node.js 示例

```javascript
// 使用 fetch API
const response = await fetch('http://localhost:8000/fetch', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    url: 'https://example.com',
    wait_for: '#main-content',
    timeout: 20,
    proxy: 'http://user:pass@proxy.example.com:8080',
    cloudflare: {
      enabled: true,
      max_retries: 3,
      click_delay: 2.0,
      challenge_timeout: 15.0
    }
  })
});

const result = await response.json();
console.log('Success:', result.success);
console.log('HTML length:', result.html.length);
```

### cURL 示例

```bash
# 简单抓取
curl -X POST "http://localhost:8000/fetch" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'

# 使用代理和等待元素
curl -X POST "http://localhost:8000/fetch" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com",
    "wait_for": "#main-content",
    "proxy": "http://user:pass@proxy.example.com:8080"
  }'

# 获取 Cookies
curl "http://localhost:8000/cookies?domain=example.com"

# 清除 Cookies
curl -X DELETE "http://localhost:8000/cookies?domain=example.com"
```

## 工作原理

### 浏览器池管理

- 服务启动时创建浏览器实例池
- 每个代理配置对应一个浏览器实例
- 使用信号量控制最大并发数
- 自动复用浏览器实例，提高性能

### Cookie 管理

- Cookies 按 `(域名, 代理)` 组合隔离存储
- 同一域名使用不同代理时，Cookies 互不干扰
- 自动加载和保存 Cookies，实现会话复用

### Cloudflare 验证

- 自动检测 Cloudflare 挑战页面
- 支持交互式验证（点击按钮）
- 可配置重试次数和超时时间
- 验证成功后自动继续加载页面

### 页面状态检测

服务会自动检测以下页面状态：

- **ok** - 正常页面
- **blocked** - 页面被阻止（检测到 "Access denied" 等文本）
- **queue** - 队列等待（检测到 "Queue-it" 等文本）
- **unreachable** - 无法访问（检测到网络错误）

## 注意事项

1. **并发限制**：默认最大并发数为 5，可根据服务器性能调整
2. **超时设置**：建议根据目标网站响应速度设置合适的超时时间
3. **代理认证**：使用带认证的代理时，确保用户名和密码正确
4. **Cloudflare 验证**：某些复杂的 Cloudflare 挑战可能无法自动解决
5. **内存使用**：长时间运行可能占用较多内存，建议定期重启服务
6. **无头模式**：生产环境建议启用无头模式（`HEADLESS = True`）

## 故障排查

### 服务无法启动

- 检查端口是否被占用
- 确认已安装所有依赖
- 检查 zendriver 是否正确安装

### 抓取失败

- 检查目标 URL 是否可访问
- 验证代理配置是否正确
- 查看响应中的 `error` 字段获取详细错误信息
- 检查 `status` 字段了解页面状态

### Cloudflare 验证失败

- 增加 `max_retries` 重试次数
- 增加 `challenge_timeout` 超时时间
- 检查是否需要更复杂的验证流程

### Cookies 未保存

- 确认请求成功（`success: true`）
- 检查域名是否正确
- 查看日志确认是否有保存错误

## 性能优化建议

1. **调整并发数**：根据服务器 CPU 和内存情况调整 `MAX_CONCURRENT`
2. **使用无头模式**：生产环境启用无头模式可减少资源占用
3. **复用 Cookies**：相同域名和代理的请求会自动复用 Cookies，减少验证次数
4. **合理设置超时**：避免过长的超时时间占用资源
5. **定期清理**：定期清理不需要的 Cookies 释放内存

## 版本信息

- 当前版本：0.3.0
- FastAPI 版本：>= 0.115.0
- Uvicorn 版本：>= 0.32.0

## 许可证

请参考项目根目录的许可证文件。

## 支持与反馈

如有问题或建议，请提交 Issue 或联系维护者。

