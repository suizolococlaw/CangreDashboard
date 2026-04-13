#!/bin/bash

# Backfill history - parse all existing OpenClaw logs

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR/../backend"

# Activate venv
source venv/bin/activate

# Run backfill
python3 << 'EOF'
import logging
from aggregator import full_scan, cleanup_old_data
from cost_analyzer import aggregate_daily_costs
from schema import SessionLocal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

print('=' * 70)
print('🦞 CangreDashboard - Full History Backfill')
print('=' * 70)
print()

# Scan all sessions
full_scan()

# Aggregate costs
print()
print('Aggregating costs...')
db = SessionLocal()
aggregate_daily_costs(db)
db.close()

# Clean up old data
print()
print('Cleaning up old data (retention: 90 days)...')
cleanup_old_data()

print()
print('✓ Backfill complete!')
print('=' * 70)
EOF
