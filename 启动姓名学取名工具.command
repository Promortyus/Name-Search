#!/bin/zsh
set -u

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
PORT="${NAME_SEARCH_PORT:-8502}"
HOST="${NAME_SEARCH_HOST:-localhost}"
URL="http://${HOST}:${PORT}"

cd "$APP_DIR" || exit 1

echo "姓名学取名工具"
echo "项目目录: $APP_DIR"
echo "访问地址: $URL"
echo ""

if command -v lsof >/dev/null 2>&1 && lsof -iTCP:"$PORT" -sTCP:LISTEN -n -P >/dev/null 2>&1; then
  echo "检测到服务已在 ${URL} 运行，正在打开浏览器..."
  open "$URL" >/dev/null 2>&1
  exit 0
fi

if [[ ! -x ".venv/bin/python" ]]; then
  echo "未找到 .venv，正在创建本地 Python 环境..."
  python3 -m venv .venv || {
    echo "创建 .venv 失败，请确认已安装 python3。"
    read -k 1 "?按任意键关闭窗口..."
    exit 1
  }
fi

if [[ ! -x ".venv/bin/streamlit" ]]; then
  echo "正在安装依赖..."
  .venv/bin/python -m pip install -r requirements.txt || {
    echo "安装依赖失败，请检查网络或 requirements.txt。"
    read -k 1 "?按任意键关闭窗口..."
    exit 1
  }
fi

echo "正在启动 Streamlit..."
open "$URL" >/dev/null 2>&1
.venv/bin/streamlit run app.py --server.port "$PORT" --server.address "$HOST"

echo ""
echo "服务已停止。"
read -k 1 "?按任意键关闭窗口..."
