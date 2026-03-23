# 抖音多开矩阵系统（支持 OpenClaw / 本地定时发布）

> by 尖叫（Todliu）（仅供学习参考）

基于 **PySide6 + QtWebEngine** 的抖音创作者平台多账号管理：多账号独立沙盒、反检测、本地 API（供 OpenClaw 等调用）、**图形界面内定时/立即自动发布** 与远程 API 触发共用同一套 `handle_openclaw_publish` 自动化逻辑。

可在软件内同时登录、管理多个抖音账号矩阵运营。**开发/日常使用以 macOS 为主**；Windows 用户可通过 **GitHub Actions 构建产物**下载免 Python 整合包（见下文）。

**跨平台**：macOS 为主开发；Windows 可通过 **GitHub Actions** 下载便携包（见文末）。

<img width="800" alt="界面截图" src="https://github.com/user-attachments/assets/0fb7c8ed-642a-4eb4-bf89-413dc9a31485" />

---

## 整体逻辑（架构摘要）

| 模块 | 行为 | 说明 |
|------|------|------|
| **账号沙盒** | 每账号独立 `QWebEngineProfile`，持久化目录 `~/Douyin_Profiles/<目录名>/` | 目录名经 `sanitize_account_name`；列表项 `UserRole` 存目录名，展示名可重命名 |
| **Flask API** | `threading.Thread(daemon=True)` 跑 `127.0.0.1:5001`，**不阻塞 Qt 主线程** | `_api_enabled` 关闭时路由返回 403；请求入 `queue.Queue`，主线程 `QTimer` 轮询执行 |
| **跨线程** | `_publish_queue` / `_log_queue` + `queue_poll_timer`（仅 API 开启时启动） | 避免在子线程直接操作 `QWebEngine` |
| **自动化** | `handle_openclaw_publish` → `switch_to` → `AutoPublishPage.set_pending_files` → `runJavaScript` + 延时拖放 | `caption` 经 `json.dumps` 注入；`post_type` 控制图文/视频 Tab |
| **定时调度** | `schedule_timer` 每秒扫描 `scheduled_tasks`，到期调用同一 `handle_openclaw_publish` | 与 API 队列独立；退出时 `aboutToQuit` 里 `stop()` |
| **退出** | `queue_poll_timer.stop()`、`schedule_timer.stop()`、`clearHttpCache()` | 降低 Qt 退出阶段崩溃风险 |

若抖音页面 DOM 变更，需单独更新 JS 选择器（见 `handle_openclaw_publish` 内脚本）。

---

## 功能亮点

| 功能 | 说明 |
|------|------|
| 多账号沙盒隔离 | 每账号独立 `QWebEngineProfile`，Cookie / 缓存互不干扰 |
| 反检测 | Stealth JS 注入（`navigator.webdriver`、插件、WebGL 等） |
| 懒加载 | 最多 50 个账号，仅当前选中加载网页 |
| 本地 API | `127.0.0.1:5001`，需在应用内开启；支持 OpenClaw 等 Agent 调用 |
| **定时发布** | 侧栏「⏱️ 创建自动任务」「📋 排期管理」：立即/定时、图文或视频，内存队列 + 1s 调度 |
| 视频 + 图文 | API 与界面任务均支持 `post_type`：`video` / `image` |
| 缓存清理 | 清 HTTP 缓存，不影响登录态 |

---

## 定时发布（已内置）

1. **创建自动任务**：选账号、类型、文件、文案；可选「立即发布」或「定时发布」（中文日期时间）。
2. **排期管理**：表格查看、刷新、立即执行选中任务、取消任务。
3. **调度引擎**：主线程 `QTimer` 每秒检查，到期则调用与 API 相同的 `handle_openclaw_publish`（**不改动其中 JS 轮询脚本**）。
4. 队列仅存**本次运行内存**，退出软件后清空。

---

## macOS 快速开始

| | macOS | Windows（源码） |
|---|---|---|
| 系统 | 12.0+ | 10 / 11 |
| Python | 3.9+ | 3.9+ |

```bash
git clone https://github.com/l15514559690-cmd/douyin-boxclaw.git
cd douyin-boxclaw
pip install -r requirements.txt
```

### 一键启动（推荐）

任选其一，在 Finder 中双击（首次会自动安装依赖）：

- **`一键启动.command`**
- **`抖音多开助手.command`**（与上一脚本等价，旧习惯可继续用）

仅需一次赋予执行权限：

```bash
chmod +x 一键启动.command 抖音多开助手.command
```

### 命令行

```bash
cd /path/to/douyin-boxclaw
pip3 install -r requirements.txt
python3 desktop_app.py
```

### 可选：桌面 .app

本地用 AppleScript 等包一层调用 `python3 desktop_app.py` 即可；需本机依赖已安装。QtWebEngine 不建议用 PyInstaller 打 mac 便携包。

---

## Windows：从 GitHub 下载整合包（免安装 Python）

本仓库含 **GitHub Actions**（`.github/workflows/build-windows.yml`），在云端 Windows 环境执行 **PyInstaller**，产出 **便携目录**（内含 **`DouyinMatrix.exe`** 及 QtWebEngine 依赖）。

### 下载方式

1. 打开本仓库在 **GitHub** 上的页面。
2. 进入 **Actions** → 选择 **「Build Windows (portable)」**（或等价工作流名）。
3. 选最近一次**绿色成功**的运行记录。
4. 在页面底部 **Artifacts** 中下载 **`DouyinMatrix_Windows`**（为 **zip**）。
5. **解压整个 zip**，进入文件夹后双击 **`DouyinMatrix.exe`**（或 **`RUN_APP.bat`**）。

> **重要**：必须保留解压后**同一目录下所有文件**（含 `QtWebEngineProcess.exe`、DLL 等），**不要只拷贝单个 exe** 到别处，否则无法运行。
> 若仓库 **尚未推送** 或 **未启用 Actions**，需先推送代码并等待工作流跑通；维护者也可将同一 zip 挂到 **Releases** 方便固定链接下载。

本地从源码在 Windows 上自行打包：`py -m PyInstaller --noconfirm --clean windows_build.spec`（需在 Windows 环境）。

---

## 项目结构（摘要）

```
douyin-boxclaw/
├── desktop_app.py          # 主程序（UI + 沙盒 + API + 定时调度）
├── requirements.txt
├── windows_build.spec      # Windows PyInstaller（CI / 本地）
├── 一键启动.command         # macOS 一键启动
├── 抖音多开助手.command     # 与上一文件等价
├── .github/workflows/
│   └── build-windows.yml   # GitHub Actions：构建 Windows 便携 zip
├── README.md
├── LICENSE
└── .gitignore
```

### 数据目录（不入库）

| 平台 | 路径 |
|------|------|
| macOS | `~/Douyin_Profiles/` |
| Windows | `%USERPROFILE%\Douyin_Profiles\` |

---

## 沙盒与反检测（摘要）

每账号独立存储路径、`ForcePersistentCookies`、UA 清洗、Stealth JS 于 `DocumentCreation` 注入。

---

## API（OpenClaw）

- **基址**：`http://127.0.0.1:5001`（仅本机；需在应用内开启 API）
- `GET /api/health`、`POST /api/publish`（`account`, `file_paths`, `caption`, `post_type`）

```bash
curl http://127.0.0.1:5001/api/health
```

自动化步骤见界面日志与源码中 `handle_openclaw_publish` 内 Step 1→6；**最终点击「发布」**默认注释，可在 `stepSix` 中取消注释 `publishBtn.click()`。

---

## 常见问题

| 问题 | 处理 |
|------|------|
| macOS `.command` 无法执行 | `chmod +x 一键启动.command`（或 `抖音多开助手.command`） |
| macOS `.app` 闪退 | 优先命令行 `python3 desktop_app.py` 看报错 |
| API 无响应 | 确认已打开「远程 API」开关；看界面日志 |
| 端口占用 | 修改 `desktop_app.py` 顶部 `API_PORT` |
| Windows 解压后打不开 | 是否只复制了 exe；必须整夹解压使用 |
| 登录丢失 | 勿删 `~/Douyin_Profiles/<账号>/webengine/` |
| GitHub 无 Artifact | 检查 Actions 是否成功；Fork 后需在仓库 **Settings → Actions** 允许 workflow |

---

## 技术栈

PySide6 / QtWebEngine · Flask（daemon 线程 + 队列 + 主线程 `QTimer`）· JS 注入 · Qt 拖放 · ClipboardEvent 粘贴 · QWebEngineScript 反检测

---

## 许可证与免责声明

[MIT License](LICENSE)。仅供学习研究，请遵守平台规则与法律法规。

使用者自行承担风险；本项目仅供技术学习与研究。
