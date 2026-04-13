#!/bin/bash

# Export costs to CSV for analysis

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR/../backend"

# Activate venv
source venv/bin/activate

# Run export
python3 << 'EOF'
import sys
import sqlite3
from datetime import datetime, timedelta
from config import DB_PATH

# Parse arguments
start_date = sys.argv[1] if len(sys.argv) > 1 else (datetime.utcnow() - timedelta(days=7)).strftime('%Y-%m-%d')
end_date = sys.argv[2] if len(sys.argv) > 2 else datetime.utcnow().strftime('%Y-%m-%d')
output_file = sys.argv[3] if len(sys.argv) > 3 else f'cost_export_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.csv'

print(f'Exporting costs from {start_date} to {end_date}...')

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Query daily metrics
cursor.execute("""
    SELECT metric_date, agent_id, model, total_tokens, total_cost, message_count
    FROM daily_metrics
    WHERE metric_date BETWEEN ? AND ?
    ORDER BY metric_date DESC, agent_id, model
""", (start_date, end_date))

rows = cursor.fetchall()
conn.close()

# Write CSV
import csv
with open(output_file, 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['Date', 'Agent', 'Model', 'Tokens', 'Cost', 'Messages'])
    for row in rows:
        writer.writerow(row)

print(f'✓ Exported {len(rows)} rows to {output_file}')
EOF
