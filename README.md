# 抖音多开矩阵系统(支持openclaw自动发布)

> by 尖叫（Todliu）（仅供学习参考）

可以同时在软件内登录绑定多个抖音账号矩阵式运营
每个账号拥有完全独立的浏览器沙盒环境，内置反检测伪装与本地 API 服务，支持 AI Agent 远程调用自动发布。

**跨平台支持：macOS / Windows**

<img width="2880" height="1904" alt="ScreenShot_2026-03-22_162511_932" src="https://github.com/user-attachments/assets/0fb7c8ed-642a-4eb4-bf89-413dc9a31485" />


---

## 功能亮点

| 功能 | 说明 |
|------|------|
| 多账号沙盒隔离 | 每个账号独立 `QWebEngineProfile`，Cookie / LocalStorage / 缓存零交叉 |
| 反检测伪装 | Stealth JS 自动注入，覆盖 `navigator.webdriver`、插件、WebGL 等 7 项指纹 |
| 懒加载 | 最多 50 个账号，仅当前选中的才加载网页，内存友好 |
| 本地 API | Flask 服务供 AI Agent（如 OpenClaw）远程触发自动发布 |
| 视频 + 图文双模式 | 支持单视频或多图文自动上传、填写文案、一键发布 |
| 缓存清理 | 一键清理 HTTP 缓存，不影响登录态 |
| 动画 UI | 深色 AI SaaS 风格界面，滑动开关、渐变指示线、Toast 通知 |

---

## 快速开始

### 环境要求

| | macOS | Windows |
|---|---|---|
| 系统 | macOS 12.0+ | Windows 10 / 11 |
| Python | 3.9+ | 3.9+ |

### 安装

```bash
git clone https://github.com/screamingworld/DouyinMatrix.git
cd DouyinMatrix
pip install -r requirements.txt
```

### 启动

```bash
# macOS
python3 desktop_app.py

# Windows
python desktop_app.py
```

或使用平台快捷方式：

| 平台 | 方式 |
|------|------|
| macOS | 双击桌面 `抖音多开矩阵系统.app`（AppleScript 壳） |
| macOS | 双击 `抖音多开助手.command` |
| Windows | 双击 `启动.bat`（自动检测环境 + 安装依赖） |
| Windows | 双击 `build_windows.bat` 打包为独立 `.exe` |

---

## 项目结构

```
DouyinMatrix/
├── desktop_app.py          # 主程序（UI + 沙盒 + API，单文件完整实现）
├── requirements.txt        # Python 依赖
├── README.md               # 本文档
├── .gitignore
├── LICENSE
├── 抖音多开助手.command     # macOS 启动脚本
├── 启动.bat                # Windows 启动脚本
└── build_windows.bat       # Windows PyInstaller 打包脚本
```

运行时数据（不入库）：

```
~/Douyin_Profiles/          # macOS
%USERPROFILE%\Douyin_Profiles\   # Windows
├── 账号A/
│   ├── webengine/          # Cookie、LocalStorage、IndexedDB
│   └── webengine_cache/    # HTTP 缓存
├── 账号B/
└── ...
```

---

## 沙盒隔离 & 反检测

### 账号隔离

每个账号使用完全独立的 `QWebEngineProfile` 实例：

| 数据类型 | 隔离方式 |
|----------|----------|
| Cookie | 独立 `PersistentStoragePath`，`ForcePersistentCookies` 策略 |
| LocalStorage / IndexedDB | 随 Profile 路径隔离 |
| HTTP 缓存 | 独立 `CachePath` |
| Session | 关闭重开不丢失登录态 |
| User-Agent | 逐 Profile 清洗 `QtWebEngine` / `HeadlessChrome` 特征 |

### Stealth JS（7 项指纹伪装）

在每个 Profile 的 `DocumentCreation` 阶段（早于页面 JS）注入：

| # | 检测点 | 伪装方式 |
|---|--------|----------|
| 1 | `navigator.webdriver` | → `undefined` |
| 2 | `window.chrome.runtime` | 注入桩函数 |
| 3 | `navigator.plugins` | 伪装 3 个标准 Chrome 插件 |
| 4 | `navigator.languages` | `['zh-CN', 'zh', 'en-US', 'en']` |
| 5 | `Permissions.query` | 拦截 Notification 检测 |
| 6 | WebGL vendor/renderer | 通用 GPU 描述 |
| 7 | `connection.rtt` | 固定 `100`，屏蔽零延迟特征 |

UA 清洗示例：

```
原始:  ...Chrome/120.0.0.0 QtWebEngine/6.x.x Safari/537.36
清洗:  ...Chrome/120.0.0.0 Safari/537.36
```

---

## API 文档

应用内置本地 Flask HTTP 服务（`127.0.0.1:5001`），供 AI Agent 或自动化脚本调用（支持openclaw）。

**启用**：点击左侧边栏的 API 服务开关。

### `GET /api/health`

```bash
curl http://127.0.0.1:5001/api/health
# {"ok": true, "app": "抖音多开矩阵系统", "port": 5001}
```

### `POST /api/publish`

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `account` | string | 是 | 账号名称（与左侧列表一致） |
| `file_paths` | string | 是 | 文件路径，多文件用 `,` 分隔 |
| `caption` | string | 否 | 发布文案 |
| `post_type` | string | 否 | `"video"`（默认）或 `"image"` |

```bash
# 发布视频
curl -X POST http://127.0.0.1:5001/api/publish \
  -H "Content-Type: application/json" \
  -d '{"account":"账号1","file_paths":"/path/to/video.mp4","caption":"测试","post_type":"video"}'

# 发布图文（多张）
curl -X POST http://127.0.0.1:5001/api/publish \
  -H "Content-Type: application/json" \
  -d '{"account":"账号2","file_paths":"/path/1.png,/path/2.png","caption":"图文测试","post_type":"image"}'
```

**响应**：`202 Accepted` → 指令已入队 | `400` → 参数缺失 | `403` → API 未启用

### Python 调用

```python
import requests

r = requests.post("http://127.0.0.1:5001/api/publish", json={
    "account": "测试账号",
    "file_paths": "/path/to/video.mp4",
    "caption": "自动发布",
    "post_type": "video"
})
print(r.json())
```

### 自动化流程

```
Step 1  点击「高清发布」→ setInterval 1s 轮询
Step 2  切换「视频/图文」Tab
Step 3  上传文件（JS 点击 + Python 拖放双保险）
Step 4  等待编辑器出现 → ClipboardEvent 粘贴文案（无超时，适配视频慢上传）
Step 5  勾选「不允许」保存（状态检测，防重复切换）
Step 6  点击「发布」（默认注释，安全模式）
```

**启用自动发布**：搜索 `stepSix`，取消 `publishBtn.click()` 的注释。

---

## 常见问题

<details>
<summary><b>macOS .app 闪退？</b></summary>

PyInstaller 打包 QtWebEngine 在 macOS ARM64 上有 GPU 兼容问题。桌面 `.app` 使用 AppleScript 壳直接调用 Python，如仍闪退请检查 `pip3 install -r requirements.txt` 是否完整。
</details>

<details>
<summary><b>Windows 中文乱码？</b></summary>

系统设置 → 区域 → 勾选「使用 Unicode UTF-8 提供全球语言支持」，或在 CMD 中先运行 `chcp 65001`。
</details>

<details>
<summary><b>Windows 防火墙弹窗？</b></summary>

API 仅监听 `127.0.0.1`（本机），可选择「取消」或「允许专用网络」，不影响功能。
</details>

<details>
<summary><b>端口 5001 被占用？</b></summary>

修改 `desktop_app.py` 顶部 `API_PORT = 5001` 为其他端口。
</details>

<details>
<summary><b>登录态丢失？</b></summary>

数据存储在 `~/Douyin_Profiles/<账号>/webengine/`。只要不删除该目录，登录态永久保持。「清理缓存」只清 HTTP 缓存，不影响 Cookie。
</details>

<details>
<summary><b>自动化发布卡住？</b></summary>

- **Step 3 卡住**：检查文件路径是否为绝对路径且文件存在
- **Step 4 卡住**：视频上传耗时较长属正常，会持续轮询
- **文案未填入**：抖音可能更新了 DOM，需更新编辑器选择器
</details>

---

## 跨平台兼容

| 特性 | macOS | Windows |
|------|-------|---------|
| 界面字体 | PingFang SC | Microsoft YaHei |
| 日志字体 | SF Mono / Menlo | Cascadia Mono / Consolas |
| 数据目录 | `~/Douyin_Profiles/` | `%USERPROFILE%\Douyin_Profiles\` |
| 快捷启动 | `.command` / `.app` | `.bat` / `.exe` |
| 底层内核 | Chromium (QtWebEngine) | Chromium (QtWebEngine) |
| API | 完全一致 | 完全一致 |

---

## 技术栈

- **GUI**：PySide6 (Qt 6) + QtWebEngine (Chromium)
- **API**：Flask（daemon 线程 + queue 跨线程通信）
- **自动化**：JS 注入 + Qt 拖放模拟 + ClipboardEvent 粘贴
- **反检测**：QWebEngineScript（DocumentCreation 阶段注入）
- **打包**：AppleScript 壳（macOS）/ PyInstaller（Windows）

---

## 许可证

[MIT License](LICENSE) — 仅供学习参考，请勿用于违反平台规则的行为。

---

## 免责声明

本项目仅供技术学习和研究目的。使用者应自行承担使用风险，开发者不对因使用本工具导致的任何问题负责。请遵守抖音平台的用户协议和相关法律法规。
