#!/usr/bin/env bash
# dispatch-los102.sh [ref] —— 派发 los102-apatch-bbr 基线（APatch + BBR + IPv6 NAT）
#
# 默认 ref=main；如果 BBR 步骤还没合进 main，用 `scripts/dispatch-los102.sh apatch-bbr`。
# 需要 GITHUB_TOKEN（或从当前 git remote 的 token 推断）。
#
# 配方 = los101 基线 + IPv6 NAT（config 已含 IP6_NF_NAT/TARGET_MASQUERADE）：
#   GOLD JSON + mi_syms_audio=1 + extra_config 末尾 BBR，无 KSU 标记。
#   los_commit=d42d2eb6c 固定（LOS 5.4.242）。
set -euo pipefail

REPO="${REPO:-birdnofoots/Mi11Pro-Droidspaces-Kernel-KSU}"
REF="${1:-main}"
TOKEN="${GITHUB_TOKEN:-$(git remote get-url origin 2>/dev/null | sed -E 's#.*x-access-token:([^@]+)@.*#\1#')}"
[ -n "$TOKEN" ] || { echo "GITHUB_TOKEN 未设置" >&2; exit 1; }

read -r -d '' INPUTS <<'JSON' || true
{
  "los_ref": "lineage-20",
  "config": "mars_factory.config",
  "jobs": "4",
  "kcflags": "-Wno-error",
  "extra_config": "-d PANIC_ON_OOPS,-d QCOM_FORCE_WDOG_BITE_ON_PANIC,-d PANIC_ON_SSR_NOTIF_TIMEOUT,-d DEBUG_POWER_MI,-e DETECT_HUNG_TASK,--set-val DEFAULT_HUNG_TASK_TIMEOUT 15,BBR",
  "logdump": "1",
  "gates": "0",
  "force_m": "CNSS2,CNSS_GENL,WCNSS_MEM_PRE_ALLOC",
  "modules": "1",
  "force_y": "CNSS_QCA6490",
  "wlanblock": "1",
  "cld_features": "0",
  "cld_ref": "",
  "los_commit": "d42d2eb6c",
  "wlan_profile": "0",
  "wlan_debug": "0",
  "mi_syms_audio": "1",
  "firmware_embed": "1",
  "hwid_deexport": "1",
  "wlan_allow": "",
  "ignore_vermagic": "1",
  "mi_syms": "1",
  "allbuiltin": "1",
  "kabi": "1",
  "modversions": "0"
}
JSON

BODY=$(python3 -c 'import json,sys; print(json.dumps({"ref":sys.argv[1],"inputs":json.load(sys.stdin)}))' "$REF" <<<"$INPUTS")

echo "POST $REPO los.yml ref=$REF"
curl -fsS -X POST \
  -H "Authorization: token $TOKEN" \
  -H "Accept: application/vnd.github+json" \
  -H "Content-Type: application/json" \
  "https://api.github.com/repos/$REPO/actions/workflows/los.yml/dispatches" \
  -d "$BODY"
echo "dispatched (HTTP 204 = OK)"
