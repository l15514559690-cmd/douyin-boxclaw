#!/bin/bash
# macOS 一键启动（与项目根目录 desktop_app.py 配套）
cd "$(dirname "$0")"

if ! python3 -c "import PySide6; import flask" 2>/dev/null; then
    echo "首次运行，正在安装依赖..."
    python3 -m pip install -q -r requirements.txt || {
        echo "依赖安装失败，请执行: pip3 install -r requirements.txt"
        read -r _
        exit 1
    }
fi

exec python3 desktop_app.py
