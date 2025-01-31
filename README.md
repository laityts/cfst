```markdown
# Cloudflare IP 优选与自动 DNS 更新工具集

一套用于从 Telegram 频道获取 Cloudflare IP 列表、测速优选、校验可用性并自动更新 Cloudflare DNS 记录的自动化工具集。

---

## 文件说明

### 1. 核心工具
| 文件名           | 功能描述                                                                 |
|------------------|--------------------------------------------------------------------------|
| `tg.py`          | 从指定 Telegram 频道下载 CSV 文件，解析并保存优选 IP 到 `cfip.txt`。      |
| `checker.py`     | 校验 IP 的可用性（Ping/TCP），清理无效 IP 并记录日志。                    |

### 2. 测速工具（IPv4/IPv6）
| 文件名           | 功能描述                                                                 |
|------------------|--------------------------------------------------------------------------|
| `cfst.py`        | 针对 IPv4 的 CloudflareSpeedTest 测速，筛选高速 IP 并生成结果文件。       |
| `cfstv6.py`      | 针对 IPv6 的测速脚本，支持多端口和多区域测试。                           |
| `cfstfd.py`      | 特定场景下的测速脚本，用于生成 `fd.txt` 和 `fdport.txt`。                 |

### 3. DNS 自动更新
| 文件名           | 功能描述                                                                 |
|------------------|--------------------------------------------------------------------------|
| `autoddns.py`    | 读取 `ip.txt`，批量更新 IPv4 的 Cloudflare DNS A 记录。                   |
| `autoddnsv6.py`  | 读取 `ipv6.txt`，批量更新 IPv6 的 Cloudflare DNS AAAA 记录。              |
| `autoddnsfd.py`  | 针对 `fd.txt` 的专用 DNS 更新脚本，支持多级域名映射。                     |

---

## 功能特性

- **自动化流程**：从 IP 获取、测速、校验到 DNS 更新全流程自动化。
- **多区域支持**：支持 HKG、SJC、LAX、FRA 等全球多个 Cloudflare 数据中心。
- **双栈支持**：IPv4 和 IPv6 双协议栈测速与 DNS 管理。
- **日志与通知**：集成日志记录和 Telegram 通知功能。
- **Git 集成**：自动提交结果到 GitHub 仓库。

---

## 依赖项

- **Python 3.8+**
- 必要库：`telethon`, `requests`, `socks`, `csv`, `logging`
- **外部工具**：
  - [CloudflareSpeedTest](https://github.com/XIU2/CloudflareSpeedTest)（自动下载）
  - Git（用于版本控制）

---

## 配置与使用

### 1. 环境变量配置
在 GitHub Secrets 或本地 `.env` 文件中设置以下变量：
```env
CLOUDFLARE_API_KEY="your_api_key"
CLOUDFLARE_EMAIL="your_email@example.com"
CLOUDFLARE_ZONE_ID="your_zone_id"
TELEGRAM_BOT_TOKEN="your_bot_token"
TELEGRAM_CHAT_ID="your_chat_id"
```

### 2. 脚本配置
- **Telegram 配置**（`tg.py`）：
  ```python
  API_ID = ''
  API_HASH = ''
  CHANNEL = ''  # 目标频道
  ```

- **测速参数**（`cfst*.py`）：
  ```python
  cfcolo_list = ["HKG", "SJC", "LAX", "FRA"]  # 测速区域
  cf_ports = [443, 2053, 2083]                # 测速端口
  ```

### 3. 运行流程
1. **获取 IP 列表**：
   ```bash
   python tg.py
   ```

2. **测速与筛选**：
   ```bash
   python cfst.py    # IPv4
   python cfstv6.py  # IPv6
   ```

3. **校验可用性**：
   ```bash
   python checker.py
   ```

4. **更新 DNS**：
   ```bash
   python autoddns.py    # IPv4
   python autoddnsv6.py  # IPv6
   ```

---

## 目录结构
```
.
├── cfip/           # 存储 IP 列表文件（ip.txt、ipv6.txt 等）
├── csv/            # 测速生成的 CSV 结果
├── logs/            # 日志文件
├── port/           # 含端口信息的 IP 列表
├── speed/          # 高速 IP 结果
├── tg.py
├── cfst*.py
├── autoddns*.py
└── checker.py
```

---

## 注意事项

1. **敏感信息保护**：切勿将 `API_KEY`、`TELEGRAM_BOT_TOKEN` 等写入公开代码。
2. **测速频率**：建议通过 Cron 或 GitHub Actions 定时运行，避免频繁请求。
3. **文件权限**：确保脚本有权限读写目录和文件（尤其是 Linux 环境）。
4. **代理配置**：如需代理，在 `tg.py` 中设置 `PROXY_*` 参数。

---

## 许可证
MIT License. 更多细节详见代码文件头部的声明。
```