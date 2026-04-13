"""Cost analysis engine for OpenClaw token consumption."""

from config import get_pricing
import logging
import re
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def _normalize_prompt_key(text):
    if not text:
        return ''
    normalized = re.sub(r'\s+', ' ', text.strip().lower())
    normalized = re.sub(r'[^a-z0-9 ]', '', normalized)
    return normalized[:180]

def calculate_message_cost(model, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens):
    """
    Calculate cost for a single message.
    
    Args:
        model: Model name (e.g., 'claude-sonnet-4.6')
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        cache_read_tokens: Number of cache read tokens
        cache_write_tokens: Number of cache write tokens
    
    Returns:
        dict with cost breakdown
    """
    pricing = get_pricing(model)
    
    # Cost per 1K tokens, so divide token count by 1000
    cost_input = (input_tokens / 1000) * pricing['input']
    cost_output = (output_tokens / 1000) * pricing['output']
    cost_cache_read = (cache_read_tokens / 1000) * pricing['cache_read']
    cost_cache_write = (cache_write_tokens / 1000) * pricing['cache_write']
    
    total_cost = cost_input + cost_output + cost_cache_read + cost_cache_write
    
    return {
        'cost_input': round(cost_input, 6),
        'cost_output': round(cost_output, 6),
        'cost_cache_read': round(cost_cache_read, 6),
        'cost_cache_write': round(cost_cache_write, 6),
        'cost_total': round(total_cost, 6),
    }

def aggregate_daily_costs(session_db):
    """
    Aggregate costs from messages into daily metrics.
    
    Args:
        session_db: SQLAlchemy session
    """
    from sqlalchemy import func, text
    from schema import Message, DailyMetric
    
    # Clear today's metrics (will be recalculated)
    from datetime import datetime
    today = datetime.utcnow().strftime('%Y-%m-%d')
    session_db.query(DailyMetric).filter_by(metric_date=today).delete()
    session_db.commit()
    
    # Group messages by date, agent, model and aggregate
    results = session_db.query(
        func.strftime('%Y-%m-%d', Message.timestamp).label('metric_date'),
        Message.agent_id,
        Message.model,
        func.sum(Message.input_tokens).label('sum_input'),
        func.sum(Message.output_tokens).label('sum_output'),
        func.sum(Message.cache_read_tokens).label('sum_cache_read'),
        func.sum(Message.cache_write_tokens).label('sum_cache_write'),
        func.sum(Message.total_tokens).label('sum_total'),
        func.sum(Message.cost_input).label('sum_cost_input'),
        func.sum(Message.cost_output).label('sum_cost_output'),
        func.sum(Message.cost_cache_read).label('sum_cost_cache_read'),
        func.sum(Message.cost_cache_write).label('sum_cost_cache_write'),
        func.sum(Message.cost_total).label('sum_cost_total'),
        func.count(Message.id).label('message_count'),
    ).group_by(
        func.strftime('%Y-%m-%d', Message.timestamp),
        Message.agent_id,
        Message.model
    ).all()
    
    for row in results:
        metric = DailyMetric(
            metric_date=row.metric_date,
            agent_id=row.agent_id,
            model=row.model,
            total_tokens=row.sum_total or 0,
            input_tokens=row.sum_input or 0,
            output_tokens=row.sum_output or 0,
            cache_read_tokens=row.sum_cache_read or 0,
            cache_write_tokens=row.sum_cache_write or 0,
            total_cost=row.sum_cost_total or 0.0,
            cost_input=row.sum_cost_input or 0.0,
            cost_output=row.sum_cost_output or 0.0,
            cost_cache=(row.sum_cost_cache_read or 0.0) + (row.sum_cost_cache_write or 0.0),
            message_count=row.message_count or 0,
        )
        session_db.add(metric)
    
    session_db.commit()
    logger.info(f'Aggregated costs into daily metrics for {len(results)} date/agent/model combinations')

def get_cost_summary(session_db):
    """Get overall cost summary (all time)."""
    from sqlalchemy import func
    from schema import Message
    
    result = session_db.query(
        func.sum(Message.total_tokens).label('total_tokens'),
        func.sum(Message.cost_total).label('total_cost'),
        func.count(Message.id).label('total_messages'),
    ).first()
    
    total_tokens = result.total_tokens or 0
    total_cost = result.total_cost or 0.0
    total_messages = result.total_messages or 0
    
    cost_per_1k = (total_cost / (total_tokens / 1000)) if total_tokens > 0 else 0.0
    
    return {
        'total_tokens': total_tokens,
        'total_cost': round(total_cost, 4),
        'total_messages': total_messages,
        'cost_per_1k_tokens': round(cost_per_1k, 4),
    }

def get_cost_by_agent(session_db):
    """Get cost breakdown by agent."""
    from sqlalchemy import func
    from schema import Message
    from datetime import datetime, timedelta
    
    results = session_db.query(
        Message.agent_id,
        func.sum(Message.total_tokens).label('total_tokens'),
        func.sum(Message.cost_total).label('total_cost'),
        func.count(Message.id).label('message_count'),
    ).group_by(Message.agent_id).all()
    
    return [
        {
            'agent_id': r.agent_id,
            'total_tokens': r.total_tokens or 0,
            'total_cost': round(r.total_cost or 0.0, 4),
            'message_count': r.message_count or 0,
        } for r in results
    ]

def get_cost_by_model(session_db):
    """Get cost breakdown by model."""
    from sqlalchemy import func
    from schema import Message
    
    results = session_db.query(
        Message.model,
        func.sum(Message.total_tokens).label('total_tokens'),
        func.sum(Message.cost_total).label('total_cost'),
        func.count(Message.id).label('message_count'),
    ).group_by(Message.model).all()
    
    return [
        {
            'model': r.model or 'unknown',
            'total_tokens': r.total_tokens or 0,
            'total_cost': round(r.total_cost or 0.0, 4),
            'message_count': r.message_count or 0,
        } for r in results
    ]

def get_cost_trend(session_db, days=7):
    """Get daily cost trend for last N days."""
    from sqlalchemy import func
    from schema import DailyMetric
    from datetime import datetime, timedelta
    
    results = session_db.query(
        DailyMetric.metric_date,
        func.sum(DailyMetric.total_cost).label('daily_cost'),
        func.sum(DailyMetric.total_tokens).label('daily_tokens'),
    ).group_by(DailyMetric.metric_date).order_by(DailyMetric.metric_date.desc()).limit(days).all()
    
    return [
        {
            'date': r.metric_date,
            'cost': round(r.daily_cost or 0.0, 4),
            'tokens': r.daily_tokens or 0,
        } for r in reversed(results)
    ]

def estimate_burn_rate(session_db, window_hours=24):
    """
    Estimate current burn rate (cost/hour and tokens/hour).
    
    Args:
        session_db: SQLAlchemy session
        window_hours: Look at last N hours
    """
    from sqlalchemy import func
    from schema import Message
    from datetime import datetime, timedelta
    
    cutoff = datetime.utcnow() - timedelta(hours=window_hours)
    
    result = session_db.query(
        func.sum(Message.total_tokens).label('tokens'),
        func.sum(Message.cost_total).label('cost'),
        func.count(Message.id).label('messages'),
    ).filter(Message.timestamp >= cutoff).first()
    
    tokens = result.tokens or 0
    cost = result.cost or 0.0
    messages = result.messages or 0
    
    if window_hours > 0:
        tokens_per_hour = tokens / window_hours
        cost_per_hour = cost / window_hours
    else:
        tokens_per_hour = 0
        cost_per_hour = 0
    
    # Project to daily / monthly if current rate continues
    daily_projection = cost_per_hour * 24
    monthly_projection = daily_projection * 30
    
    return {
        'window_hours': window_hours,
        'tokens_in_window': tokens,
        'cost_in_window': round(cost, 4),
        'messages_in_window': messages,
        'tokens_per_hour': round(tokens_per_hour, 2),
        'cost_per_hour': round(cost_per_hour, 6),
        'projected_daily_cost': round(daily_projection, 4),
        'projected_monthly_cost': round(monthly_projection, 2),
    }


def get_cost_by_prompt(session_db, limit=25, agent_id=None, start_date=None, end_date=None):
    """Return per-prompt cost rows and repeated-prompt hotspots."""
    from schema import Message

    query = session_db.query(Message).order_by(Message.session_id.asc(), Message.timestamp.asc(), Message.id.asc())
    if agent_id:
        query = query.filter(Message.agent_id == agent_id)

    if start_date:
        start_bound = datetime.fromisoformat(start_date)
        query = query.filter(Message.timestamp >= start_bound)

    if end_date:
        end_bound = datetime.fromisoformat(end_date) + timedelta(days=1)
        query = query.filter(Message.timestamp < end_bound)

    rows = query.all()

    last_user_prompt_by_session = {}
    prompt_rows = []

    for row in rows:
        preview = (row.content_preview or '').strip()

        if row.role == 'user':
            last_user_prompt_by_session[row.session_id] = preview
            continue

        if row.role != 'assistant' or (row.cost_total or 0) <= 0:
            continue

        prompt_preview = last_user_prompt_by_session.get(row.session_id) or preview or '(No prompt preview captured)'
        prompt_rows.append({
            'timestamp': row.timestamp.isoformat() if row.timestamp else None,
            'agent_id': row.agent_id,
            'session_id': row.session_id,
            'model': row.model or 'unknown',
            'prompt_preview': prompt_preview,
            'cost': round(row.cost_total or 0.0, 6),
            'tokens': row.total_tokens or 0,
            'input_tokens': row.input_tokens or 0,
            'output_tokens': row.output_tokens or 0,
            'cache_read_tokens': row.cache_read_tokens or 0,
            'cache_write_tokens': row.cache_write_tokens or 0,
        })

    prompt_rows.sort(key=lambda item: item['cost'], reverse=True)
    top_rows = prompt_rows[:limit]

    repeated = {}
    for row in prompt_rows:
        prompt_key = _normalize_prompt_key(row['prompt_preview'])
        if not prompt_key:
            continue

        group = repeated.setdefault(prompt_key, {
            'prompt_preview': row['prompt_preview'],
            'occurrences': 0,
            'total_cost': 0.0,
            'total_tokens': 0,
            'max_cost': 0.0,
            'agents': set(),
        })
        group['occurrences'] += 1
        group['total_cost'] += row['cost']
        group['total_tokens'] += row['tokens']
        group['max_cost'] = max(group['max_cost'], row['cost'])
        group['agents'].add(row['agent_id'])

    repeated_rows = []
    repeated_spend = 0.0
    repeated_turns = 0
    repeated_potential_savings = 0.0
    for group in repeated.values():
        if group['occurrences'] < 2:
            continue
        potential_savings = max(group['total_cost'] - group['max_cost'], 0.0)
        merge_opportunity_score = (potential_savings / group['total_cost'] * 100) if group['total_cost'] > 0 else 0.0
        repeated_spend += group['total_cost']
        repeated_turns += group['occurrences']
        repeated_potential_savings += potential_savings
        repeated_rows.append({
            'prompt_preview': group['prompt_preview'],
            'occurrences': group['occurrences'],
            'total_cost': round(group['total_cost'], 6),
            'avg_cost': round(group['total_cost'] / group['occurrences'], 6),
            'max_cost': round(group['max_cost'], 6),
            'potential_savings': round(potential_savings, 6),
            'merge_opportunity_score': round(merge_opportunity_score, 2),
            'total_tokens': group['total_tokens'],
            'agents': sorted(group['agents']),
        })

    repeated_rows.sort(key=lambda item: (item['total_cost'], item['occurrences']), reverse=True)

    total_cost = sum(row['cost'] for row in prompt_rows)
    highest_cost = top_rows[0]['cost'] if top_rows else 0.0
    avg_cost = (total_cost / len(prompt_rows)) if prompt_rows else 0.0
    merge_opportunity_score = (repeated_potential_savings / total_cost * 100) if total_cost > 0 else 0.0

    return {
        'filters': {
            'agent_id': agent_id,
            'start_date': start_date,
            'end_date': end_date,
            'limit': limit,
        },
        'summary': {
            'billable_prompts': len(prompt_rows),
            'avg_cost': round(avg_cost, 6),
            'highest_cost': round(highest_cost, 6),
            'repeated_prompt_spend': round(repeated_spend, 6),
            'repeated_prompt_turns': repeated_turns,
            'potential_savings': round(repeated_potential_savings, 6),
            'merge_opportunity_score': round(merge_opportunity_score, 2),
        },
        'prompts': top_rows,
        'repeated_prompts': repeated_rows[:10],
    }
