#!/bin/bash

# Export prompt-cost analysis rows to CSV

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR/../backend"

source venv/bin/activate

python3 - "$@" <<'EOF'
import csv
import sys
from datetime import datetime, timedelta

from schema import SessionLocal
from cost_analyzer import get_cost_by_prompt

start_date = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] else (datetime.utcnow() - timedelta(days=7)).strftime('%Y-%m-%d')
end_date = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] else datetime.utcnow().strftime('%Y-%m-%d')
agent_id = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] else None
output_file = sys.argv[4] if len(sys.argv) > 4 and sys.argv[4] else f'prompt_cost_export_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.csv'

session_db = SessionLocal()
try:
    payload = get_cost_by_prompt(
        session_db,
        limit=100000,
        agent_id=agent_id,
        start_date=start_date,
        end_date=end_date,
    )
finally:
    session_db.close()

rows = payload['prompts']

with open(output_file, 'w', newline='') as handle:
    writer = csv.writer(handle)
    writer.writerow([
        'Timestamp',
        'Agent',
        'Session ID',
        'Model',
        'Prompt Preview',
        'Cost',
        'Tokens',
        'Input Tokens',
        'Output Tokens',
        'Cache Read Tokens',
        'Cache Write Tokens',
    ])
    for row in rows:
        writer.writerow([
            row['timestamp'],
            row['agent_id'],
            row['session_id'],
            row['model'],
            row['prompt_preview'],
            row['cost'],
            row['tokens'],
            row['input_tokens'],
            row['output_tokens'],
            row['cache_read_tokens'],
            row['cache_write_tokens'],
        ])

print(f"✓ Exported {len(rows)} prompt-cost rows to {output_file}")
EOF
