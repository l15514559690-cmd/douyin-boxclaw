# 抖音多开矩阵系统（支持 OpenClaw / 本地定时发布）

> by 尖叫（Todliu）（仅供学习参考）

基于 **PySide6 + QtWebEngine** 的抖音创作者平台多账号管理：多账号独立沙盒、反检测、本地 API（供 OpenClaw 等调用）、**图形界面内定时/立即自动发布** 与远程 API 触发共用同一套 `handle_openclaw_publish` 自动化逻辑。

可在软件内同时登录、管理多个抖音账号矩阵运营。

**跨平台**：macOS 为主开发；Windows 可通过 **GitHub Actions** 下载便携包（见文末）。

<img width="800" alt="界面截图" src="https://github.com/user-attachments/assets/0fb7c8ed-642a-4eb4-bf89-413dc9a31485" />

---

## 功能亮点

| 功能 | 说明 |
|------|------|
| 多账号沙盒隔离 | 每账号独立 `QWebEngineProfile`，Cookie / 缓存互不干扰 |
| 反检测 | Stealth JS 注入（`navigator.webdriver`、插件、WebGL 等） |
| 懒加载 | 最多 50 个账号 |
| 本地 API | `127.0.0.1:5001`，支持 OpenClaw 等 Agent 调用 |
| **定时发布** | 侧栏「⏱️ 创建自动任务」「📋 排期管理」：立即/定时、图文或视频，内存队列 + 1s 调度 |
| 视频 + 图文 | `post_type`：`video` / `image` |
| 缓存清理 | 清 HTTP 缓存，不影响登录态 |

---

## 定时发布（已内置）

1. **创建自动任务**：选账号、类型、文件、文案；可选「立即发布」或「定时发布」（中文日期时间）。  
2. **排期管理**：表格查看、刷新、立即执行选中任务、取消任务。  
3. **调度引擎**：主线程 `QTimer` 每秒检查，到期则调用与 API 相同的 `handle_openclaw_publish`（**不改动其中 JS 轮询脚本**）。  
4. 队列仅存**本次运行内存**，退出软件后清空。

---

## 快速开始

### 环境

| | macOS | Windows（源码） |
|---|---|---|
| 系统 | 12.0+ | 10 / 11 |
| Python | 3.9+ | 3.9+ |

```bash
git clone https://github.com/l15514559690-cmd/douyin-boxclaw.git
cd douyin-boxclaw
pip install -r requirements.txt
```

**macOS**：`python3 desktop_app.py`，或双击 **`抖音多开助手.command`**（若仓库内提供）。

**Windows 便携包（免装 Python）**：打开本仓库 **Actions** → **Build Windows**（或等价工作流）→ 成功运行后，在 **Artifacts** 中下载 zip，**整包解压**后运行 **`DouyinMatrix.exe`**（须保留目录内全部文件，勿只拷单个 exe）。

---

## 项目结构（摘要）

```
├── desktop_app.py       # 主程序（UI + 沙盒 + API + 定时调度）
├── requirements.txt
├── windows_build.spec   # Windows PyInstaller（CI / 本地）
├── .github/workflows/   # 云端构建 Windows 便携包
├── README.md
└── LICENSE
```

数据目录：`~/Douyin_Profiles/`（Windows：`%USERPROFILE%\Douyin_Profiles\`）。

---

## API（OpenClaw）

- 基址：`http://127.0.0.1:5001`，需在应用内**开启 API 服务**。  
- `GET /api/health`、`POST /api/publish`（`account`, `file_paths`, `caption`, `post_type`）。

自动化步骤见界面日志与源码中 `handle_openclaw_publish` 内 Step 1→6；**最终点击「发布」**默认注释，可在 `stepSix` 中取消注释 `publishBtn.click()`。

---

## 常见问题

- **macOS .app 闪退**：优先命令行 `python3 desktop_app.py` 看报错；QtWebEngine 不建议用 PyInstaller 打 mac 包，可用 AppleScript 调系统 Python。  
- **端口占用**：改 `desktop_app.py` 中 `API_PORT`。  
- **登录丢失**：勿删 `~/Douyin_Profiles/<账号>/webengine/`。

---

## 技术栈

PySide6 / QtWebEngine · Flask（daemon 线程 + 队列）· JS 注入 · Qt 拖放 · ClipboardEvent 粘贴 · QWebEngineScript 反检测

---

## 许可证与免责声明

[MIT License](LICENSE)。仅供学习研究，请遵守平台规则与法律法规。
