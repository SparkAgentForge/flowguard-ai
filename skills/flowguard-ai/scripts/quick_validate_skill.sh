#!/usr/bin/env bash
set -euo pipefail

script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
skill_dir="$(CDPATH= cd -- "$script_dir/.." && pwd)"
validator="${FLOWGUARD_SKILL_VALIDATOR:-}"
skill_python="${FLOWGUARD_SKILL_PYTHON:-python3}"

if [[ -z "$validator" ]]; then
  codex_root="${CODEX_HOME:-}"
  if [[ -n "$codex_root" && -f "$codex_root/skills/.system/skill-creator/scripts/quick_validate.py" ]]; then
    validator="$codex_root/skills/.system/skill-creator/scripts/quick_validate.py"
  elif [[ -f "$HOME/.codex/skills/.system/skill-creator/scripts/quick_validate.py" ]]; then
    validator="$HOME/.codex/skills/.system/skill-creator/scripts/quick_validate.py"
  fi
fi

if [[ -z "$validator" || ! -f "$validator" ]]; then
  printf '%s\n' "未找到 skill-creator quick_validate.py。请设置 FLOWGUARD_SKILL_VALIDATOR 后重试。" >&2
  exit 2
fi

if ! "$skill_python" -c 'import yaml' >/dev/null 2>&1; then
  printf '%s\n' "校验器依赖 PyYAML，但当前 Python 未安装。请设置 FLOWGUARD_SKILL_PYTHON 指向已有环境，或由环境维护者安装后重试。" >&2
  exit 2
fi

"$skill_python" "$validator" "$skill_dir"

for required_file in \
  "$skill_dir/SKILL.md" \
  "$skill_dir/agents/openai.yaml" \
  "$skill_dir/references/project-scope.md" \
  "$skill_dir/references/flowguard-architecture.md" \
  "$skill_dir/references/deepstream-integration.md" \
  "$skill_dir/references/step5-rustfs-contract.md" \
  "$skill_dir/references/deployment-runbook.md" \
  "$skill_dir/references/acceptance-matrix.md"; do
  [[ -f "$required_file" ]] || { printf '缺少文件: %s\n' "$required_file" >&2; exit 1; }
done

[[ -x "$skill_dir/scripts/server_acceptance.sh" ]] || {
  printf '%s\n' "server_acceptance.sh 不可执行" >&2
  exit 1
}

printf '%s\n' "FlowGuard AI skill structure validated."
