#!/usr/bin/env bash
# 从 state 分支恢复 data/proxy.json 和 data/regions.json 到工作区，
# 作为 udpxy.py / subs.py 的延续源。
# 用 git show 直接写文件（不动 index），避免污染 main 的提交。
set -e

git fetch origin state:refs/remotes/origin/state 2>/dev/null || true

if git rev-parse --verify origin/state >/dev/null 2>&1; then
  mkdir -p data
  git show origin/state:data/proxy.json > data/proxy.json 2>/dev/null || true
  git show origin/state:data/regions.json > data/regions.json 2>/dev/null || true
  git show origin/state:data/proxy_hotel.json > data/proxy_hotel.json 2>/dev/null || true
  echo "已从 state 分支恢复延续源（proxy.json / regions.json / proxy_hotel.json）"
else
  echo "state 分支不存在，本次从头采集"
fi
