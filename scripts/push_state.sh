#!/usr/bin/env bash
# 把敏感数据（中转地址池 / 地区表）推到 state 分支。
# 这些文件不再放进 main（GitHub Pages 会公开 main 的全部内容），
# 只有 state 分支保存，作为下一次采集的「延续源」。
#
# 用法：在 workflow 的 main checkout 工作区里，运行完采集后调用本脚本。
#   本脚本用独立 worktree checkout state 分支，把 data/proxy.json 和
#   data/regions.json 复制过去提交并推送，不影响主工作区的 main 提交。
set -e

git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

git fetch origin state:refs/remotes/origin/state 2>/dev/null || true

if git rev-parse --verify origin/state >/dev/null 2>&1; then
  git worktree add --detach /tmp/state-worktree origin/state
else
  git worktree add -b state /tmp/state-worktree
fi

mkdir -p /tmp/state-worktree/data
cp data/proxy.json /tmp/state-worktree/data/proxy.json 2>/dev/null || true
cp data/regions.json /tmp/state-worktree/data/regions.json 2>/dev/null || true

cd /tmp/state-worktree
git add -f data/proxy.json data/regions.json
if git diff --cached --quiet; then
  echo "state 分支无变化，跳过提交"
else
  git commit -m "chore(state): 更新中转池 $(date -u '+%Y-%m-%d %H:%M UTC')"
  git push origin HEAD:state
  echo "state 分支已更新"
fi

cd "$GITHUB_WORKSPACE"
git worktree remove /tmp/state-worktree --force 2>/dev/null || true
