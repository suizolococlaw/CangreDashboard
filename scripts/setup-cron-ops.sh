#!/usr/bin/env bash
# setup-cron-ops.sh — Migrate heartbeat monitoring tasks to cheap isolated ops-agent cron jobs.
# Ref: https://docs.openclaw.ai/cli/cron
#
# Usage:
#   bash scripts/setup-cron-ops.sh
#
# After running, verify with:
#   openclaw cron list
#
# To receive Telegram alerts for a job, run:
#   openclaw cron edit <job-id> --announce --channel telegram --to "<chat_id>"

set -euo pipefail

echo "Registering ops-agent cron jobs..."

openclaw cron add \
  --name "ops:gateway-health" \
  --cron "0 * * * *" \
  --session isolated \
  --agent ops \
  --model "github-copilot/gpt-4.1" \
  --light-context \
  --no-deliver \
  --message "Run \`openclaw gateway status\`. Reply HEARTBEAT_OK if healthy. If not running or returning errors, attempt a restart. One short line if issue persists."

openclaw cron add \
  --name "ops:disk-check" \
  --cron "0 */2 * * *" \
  --session isolated \
  --agent ops \
  --model "github-copilot/gpt-4.1" \
  --light-context \
  --no-deliver \
  --message "Run \`df -h\`. Reply HEARTBEAT_OK if no partition exceeds 85%. Otherwise one line: partition name and usage percentage."

openclaw cron add \
  --name "ops:memory-cpu" \
  --cron "30 */2 * * *" \
  --session isolated \
  --agent ops \
  --model "github-copilot/gpt-4.1" \
  --light-context \
  --no-deliver \
  --message "Run \`vm_stat\` and \`uptime\`. Reply HEARTBEAT_OK if memory pressure is normal and 15-min load average is below 4.0. Otherwise one short line."

openclaw cron add \
  --name "ops:stuck-sessions" \
  --cron "15 * * * *" \
  --session isolated \
  --agent ops \
  --model "github-copilot/gpt-4.1" \
  --light-context \
  --no-deliver \
  --message "Run \`openclaw gateway status\`. Check for agent sessions processing for over 30 minutes. Reply HEARTBEAT_OK if none found. Otherwise one line per stuck session."

openclaw cron add \
  --name "ops:agent-health" \
  --cron "45 * * * *" \
  --session isolated \
  --agent ops \
  --model "github-copilot/gpt-4.1" \
  --light-context \
  --no-deliver \
  --message "Run \`sessions_list\` and check for agents with stale or errored sessions (no response in over 2 hours with open sessions). Reply HEARTBEAT_OK if all healthy. Otherwise one line per affected agent."

openclaw cron add \
  --name "ops:config-drift" \
  --cron "0 0 * * 0" \
  --session isolated \
  --agent ops \
  --model "github-copilot/gpt-4.1" \
  --light-context \
  --no-deliver \
  --message "Run \`ls -la ~/.openclaw/openclaw.json\`. Reply HEARTBEAT_OK if last-modified within 30 days. Otherwise note it may need a review."

echo ""
echo "Done. Verify with: openclaw cron list"
echo ""
echo "Next steps:"
echo "  1. Run 'openclaw gateway restart' to load the new ops agent."
echo "  2. Optionally add Telegram delivery: openclaw cron edit <job-id> --announce --channel telegram --to '<chat_id>'"
echo "  3. Strip the 'tasks:' block from ~/.openclaw/workspace/HEARTBEAT.md since tasks are now managed by cron."
