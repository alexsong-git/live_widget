#!/usr/bin/env bash
# Freestyle Job「Execute shell」里可：bash jenkins/freestyle-build.sh
# 需在同一 shell 前注入环境变量 PD_ROUTING_KEY（见 jenkins/FREESTYLE.md）

set -u

python3 -m venv .venv
# shellcheck disable=SC1091
. .venv/bin/activate
pip install -r requirements.txt
playwright install chromium

pytest --alluredir=allure-results
RC=$?

if [ "$RC" -ne 0 ] && [ -n "${PD_ROUTING_KEY:-}" ]; then
  curl -sS -X POST 'https://events.pagerduty.com/v2/enqueue' \
    -H 'Content-Type: application/json' \
    -d "{\"routing_key\":\"${PD_ROUTING_KEY}\",\"event_action\":\"trigger\",\"payload\":{\"summary\":\"live_widget pytest failed\",\"severity\":\"critical\",\"source\":\"jenkins-freestyle\",\"custom_details\":{\"job\":\"${JOB_NAME:-}\",\"build\":\"${BUILD_NUMBER:-}\",\"url\":\"${BUILD_URL:-}\"}}}"
fi

exit "$RC"
