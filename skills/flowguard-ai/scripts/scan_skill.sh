#!/usr/bin/env bash
set -euo pipefail

script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
skill_dir="$(CDPATH= cd -- "$script_dir/.." && pwd)"

if ! command -v rg >/dev/null 2>&1; then
  printf '%s\n' "扫描需要 rg；请由环境维护者提供它，不要由 Skill 自动安装。" >&2
  exit 2
fi

scan_paths=("$skill_dir")
patterns=(
  '-----BEGIN (RSA|OPENSSH|EC|DSA) PRIVATE KEY-----'
  '(ghp|github_pat|glpat|xox[baprs])-[A-Za-z0-9_-]{12,}'
  'https?://[^[:space:]/]+:[^[:space:]/]+@'
)

for pattern in "${patterns[@]}"; do
  if rg --hidden --glob '!skill.oms.manifest' --glob '!skill.oms.sig' \
    -n -e "$pattern" "${scan_paths[@]}"; then
    printf '扫描发现疑似敏感内容: %s\n' "$pattern" >&2
    exit 1
  fi
done

bash -n "$skill_dir/scripts/quick_validate_skill.sh"
bash -n "$skill_dir/scripts/server_acceptance.sh"
bash -n "$skill_dir/scripts/scan_skill.sh"
bash -n "$skill_dir/scripts/sign_skill_manifest.sh"

printf '%s\n' "FlowGuard AI skill safety scan passed."
