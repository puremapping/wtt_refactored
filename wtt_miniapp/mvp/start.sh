#!/usr/bin/env bash
# wtt_miniapp MVP — 启动三个服务
# 用法：在 Git Bash / MSYS 下  bash start.sh
# 依赖：Node >= 18（wxa-runner）、主项目 .venv（Python 3.13 + fastapi）
# ⚠️ 不需要微信开发者工具；wxa-runner 自带内置基础库 3.7.0
# ⚠️ AI 讲解需要 BUPT key：环境变量 WTT_BUPT_API_KEY，
#    或本机文件 C:/Users/mengzhe/Desktop/wtt_miniapp_bupt.txt（不进仓库）
set -e

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
PY="$ROOT/.venv/Scripts/python.exe"

echo "== 平台侧 / context 导出 (127.0.0.1:8100) =="
"$PY" "$HERE/platform/server.py" &
PLAT_PID=$!

echo "== 模拟景区侧 / AI 讲解代理 (127.0.0.1:8200) =="
"$PY" "$HERE/scenic_proxy/server.py" &
LLM_PID=$!

echo "== 小程序模拟器 (127.0.0.1:3401) =="
(cd "$HERE" && npx -y wxa-runner dev ./miniprogram --port 3401 --host) &
MP_PID=$!

trap 'kill $PLAT_PID $LLM_PID $MP_PID 2>/dev/null' EXIT INT TERM

echo ""
echo "打开：http://127.0.0.1:3401/"
echo "平台 health：      http://127.0.0.1:8100/health"
echo "景区代理 health：  http://127.0.0.1:8200/health"
echo "按 Ctrl-C 停三个服务"
wait
