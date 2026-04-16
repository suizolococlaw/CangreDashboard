import os
import json
from pathlib import Path

# Data source configuration
OPENCLAW_HOME = os.getenv('OPENCLAW_HOME', os.path.expanduser('~/.openclaw'))
AGENTS_DIR = os.path.join(OPENCLAW_HOME, 'agents')
LOGS_DIR = os.path.join(OPENCLAW_HOME, 'logs')

def get_active_agent_ids():
    """Return the set of agent IDs currently defined in openclaw.json.
    Falls back to directory-based discovery if the file is missing or malformed."""
    config_path = os.path.join(OPENCLAW_HOME, 'openclaw.json')
    try:
        with open(config_path) as f:
            data = json.load(f)
        agents = data.get('agents', {}).get('list', [])
        ids = {a['id'] for a in agents if 'id' in a}
        if ids:
            return ids
    except Exception:
        pass
    # Fallback: any subdirectory in AGENTS_DIR
    try:
        return {d for d in os.listdir(AGENTS_DIR) if os.path.isdir(os.path.join(AGENTS_DIR, d))}
    except Exception:
        return set()

# Database configuration
DB_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.expanduser('~/.openclaw/cangre_dashboard.db')
DATABASE_URL = f'sqlite:///{DB_PATH}'

# Flask configuration
FLASK_HOST = '127.0.0.1'
FLASK_PORT = 5001
DEBUG = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'

# Data retention
RETENTION_DAYS = 90

# Budget cap (USD/month). Change here to update the dashboard gauge.
MONTHLY_BUDGET = 10.0

# Date from which GitHub Copilot billing started. Data before this is ignored.
COPILOT_START_DATE = '2026-04-10'

# April 2026 is treated as setup/learning — noted but not penalised.
SETUP_MONTHS = ['2026-04']

# Pricing configuration ($/token)
# GitHub Copilot subscription: Claude Sonnet is a premium model (billed).
# GPT-4o, GPT-4.1, GPT-4o-mini, GPT-5-mini are included free in the plan.
PRICING_TIERS = {
    # --- Billed models (premium tokens on Copilot) ---
    'claude-sonnet-4.6': {
        'input': 0.003,              # $0.003 per 1K input tokens
        'output': 0.015,             # $0.015 per 1K output tokens
        'cache_read': 0.0003,
        'cache_write': 0.0003,
    },
    # --- Free models included in GitHub Copilot subscription ---
    'gpt-4o': {'input': 0.0, 'output': 0.0, 'cache_read': 0.0, 'cache_write': 0.0},
    'gpt-4o-2024-08-06': {'input': 0.0, 'output': 0.0, 'cache_read': 0.0, 'cache_write': 0.0},
    'gpt-4o-mini': {'input': 0.0, 'output': 0.0, 'cache_read': 0.0, 'cache_write': 0.0},
    'gpt-4.1': {'input': 0.0, 'output': 0.0, 'cache_read': 0.0, 'cache_write': 0.0},
    'gpt-4.1-mini': {'input': 0.0, 'output': 0.0, 'cache_read': 0.0, 'cache_write': 0.0},
    'github-copilot/gpt-4.1': {'input': 0.0, 'output': 0.0, 'cache_read': 0.0, 'cache_write': 0.0},
    'gpt-5.4': {'input': 0.0, 'output': 0.0, 'cache_read': 0.0, 'cache_write': 0.0},
    'gpt-5.4-mini': {'input': 0.0, 'output': 0.0, 'cache_read': 0.0, 'cache_write': 0.0},
    'gpt-5.2': {'input': 0.0, 'output': 0.0, 'cache_read': 0.0, 'cache_write': 0.0},
    'default': {
        'input': 0.001,
        'output': 0.001,
        'cache_read': 0.0001,
        'cache_write': 0.0001,
    }
}

def get_pricing(model):
    """Get pricing for a model, fallback to default."""
    return PRICING_TIERS.get(model, PRICING_TIERS['default'])

def validate_config():
    """Validate that required directories exist."""
    if not os.path.isdir(AGENTS_DIR):
        raise Exception(f'AGENTS_DIR not found: {AGENTS_DIR}')
    if not os.path.isdir(LOGS_DIR):
        raise Exception(f'LOGS_DIR not found: {LOGS_DIR}')
    print(f'✓ Config validated')
    print(f'  - OPENCLAW_HOME: {OPENCLAW_HOME}')
    print(f'  - DB_PATH: {DB_PATH}')
