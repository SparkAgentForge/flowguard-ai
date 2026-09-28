#!/usr/bin/env bash
set -euo pipefail

script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
skill_dir="$(CDPATH= cd -- "$script_dir/.." && pwd)"
signing_key="${FLOWGUARD_SKILL_SIGNING_KEY:-}"
manifest_path="${1:-$skill_dir/skill.oms.manifest}"
signature_path="${2:-$skill_dir/skill.oms.sig}"

if [[ -z "$signing_key" || ! -f "$signing_key" ]]; then
  printf '%s\n' "请通过 FLOWGUARD_SKILL_SIGNING_KEY 提供已有的签名私钥；Skill 不会生成或下载私钥。" >&2
  exit 2
fi
if ! command -v openssl >/dev/null 2>&1; then
  printf '%s\n' "签名需要 openssl；请由环境维护者提供它，不要由 Skill 自动安装。" >&2
  exit 2
fi

manifest_tmp="$(mktemp "${TMPDIR:-/tmp}/flowguard-skill-manifest.XXXXXX")"
trap 'rm -f "$manifest_tmp"' EXIT

while IFS= read -r file; do
  rel="${file#"$skill_dir"/}"
  digest="$(openssl dgst -sha256 "$file" | awk '{print $NF}')"
  printf '%s  %s\n' "$digest" "$rel"
done < <(find "$skill_dir" -type f \
  ! -name 'skill.oms.manifest' ! -name 'skill.oms.sig' -print | LC_ALL=C sort) > "$manifest_tmp"

mkdir -p "$(dirname -- "$manifest_path")" "$(dirname -- "$signature_path")"
mv "$manifest_tmp" "$manifest_path"
trap - EXIT
openssl dgst -sha256 -sign "$signing_key" -out "$signature_path" "$manifest_path"
printf 'Manifest: %s\nSignature: %s\n' "$manifest_path" "$signature_path"
