import os
from pathlib import Path

# Data source configuration
OPENCLAW_HOME = os.getenv('OPENCLAW_HOME', os.path.expanduser('~/.openclaw'))
AGENTS_DIR = os.path.join(OPENCLAW_HOME, 'agents')
LOGS_DIR = os.path.join(OPENCLAW_HOME, 'logs')

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

# Pricing configuration ($/token)
# When real billing is enabled, update these values
PRICING_TIERS = {
    'claude-sonnet-4.6': {
        'input': 0.003,              # $0.003 per 1K input tokens
        'output': 0.015,             # $0.015 per 1K output tokens
        'cache_read': 0.0003,        # $0.0003 per 1K cache read tokens
        'cache_write': 0.0003,       # $0.0003 per 1K cache write tokens
    },
    'gpt-4o-2024-08-06': {
        'input': 0.005,
        'output': 0.015,
        'cache_read': 0.00075,
        'cache_write': 0.00075,
    },
    'gpt-5.4': {
        'input': 0.01,
        'output': 0.03,
        'cache_read': 0.001,
        'cache_write': 0.001,
    },
    'gpt-4.1': {
        'input': 0.002,       # $2.00 per 1M input tokens
        'output': 0.008,      # $8.00 per 1M output tokens
        'cache_read': 0.0005, # $0.50 per 1M cached input tokens
        'cache_write': 0.0,
    },
    'github-copilot/gpt-4.1': {
        'input': 0.002,
        'output': 0.008,
        'cache_read': 0.0005,
        'cache_write': 0.0,
    },
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
