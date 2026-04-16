"""JSONL session aggregator - parses OpenClaw session logs."""

import json
import os
import re
from datetime import datetime
from pathlib import Path
from collections import defaultdict
from schema import SessionLocal, Agent, Session, Message, DailyMetric, init_db
from cost_analyzer import calculate_message_cost
from config import AGENTS_DIR, RETENTION_DAYS, get_active_agent_ids
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _usage_value(usage, *keys):
    """Return the first present usage key as int."""
    for key in keys:
        value = usage.get(key)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                return 0
    return 0


def _extract_delegated_agent(msg_data):
    """Extract delegated agent id from tool call arguments, if present."""
    if not isinstance(msg_data, dict):
        return None

    content = msg_data.get('content', [])
    if not isinstance(content, list):
        return None

    for part in content:
        if not isinstance(part, dict):
            continue
        if part.get('type') != 'toolCall':
            continue

        args = part.get('arguments', {})
        if not isinstance(args, dict):
            continue

        delegated = args.get('agentId') or args.get('agent_id')
        if delegated:
            return str(delegated)

    return None


def _clean_preview_text(text):
    """Reduce noisy bridge metadata to a readable prompt preview."""
    if not text:
        return ''

    text = re.sub(r'```.*?```', ' ', text, flags=re.DOTALL)
    text = text.replace('Conversation info (untrusted metadata):', ' ')
    text = text.replace('Sender (untrusted metadata):', ' ')
    text = text.replace('Replied message (untrusted, for context):', ' ')
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:280]


def _extract_content_preview(msg_data):
    """Extract a concise text preview from message content."""
    if not isinstance(msg_data, dict):
        return ''

    content = msg_data.get('content', [])
    if isinstance(content, str):
        return _clean_preview_text(content)

    if not isinstance(content, list):
        return ''

    parts = []
    for part in content:
        if not isinstance(part, dict):
            continue

        part_type = part.get('type')
        if part_type == 'text' and part.get('text'):
            parts.append(part.get('text'))
        elif part_type == 'toolCall':
            tool_name = part.get('name', 'tool')
            args = part.get('arguments', {})
            if isinstance(args, dict):
                hint = args.get('query') or args.get('command') or args.get('task') or args.get('path') or args.get('agentId')
                if hint:
                    parts.append(f'[{tool_name}] {hint}')
                else:
                    parts.append(f'[{tool_name}]')

    return _clean_preview_text(' '.join(parts))

def parse_jsonl_file(filepath):
    """Parse a JSONL file and yield events."""
    try:
        with open(filepath, 'r') as f:
            for line_num, line in enumerate(f, 1):
                if line.strip():
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError as e:
                        logger.warning(f'Invalid JSON at {filepath}:{line_num}: {str(e)[:50]}')
    except FileNotFoundError:
        logger.warning(f'File not found: {filepath}')

def process_agent_sessions(agent_id):
    """Process all session files for an agent."""
    sessions_dir = os.path.join(AGENTS_DIR, agent_id, 'sessions')
    if not os.path.isdir(sessions_dir):
        logger.debug(f'Sessions dir not found: {sessions_dir}')
        return

    db = SessionLocal()
    try:
        # Get or create agent record
        agent = db.query(Agent).filter_by(agent_id=agent_id).first()
        if not agent:
            agent = Agent(agent_id=agent_id, agent_name=agent_id)
            db.add(agent)
            db.commit()
            logger.info(f'Created agent: {agent_id}')

        for jsonl_file in Path(sessions_dir).glob('*.jsonl'):
            if '.deleted.' in jsonl_file.name:
                continue
            
            logger.debug(f'Processing: {jsonl_file.name}')
            process_session_file(db, agent_id, jsonl_file, agent)
            
    except Exception as e:
        logger.error(f'Error processing agent {agent_id}: {e}')
        db.rollback()
    finally:
        db.close()

def process_session_file(db, agent_id, filepath, agent_obj):
    """Process a single session JSONL file."""
    session_id = None
    session_obj = None
    
    for event in parse_jsonl_file(filepath):
        event_type = event.get('type')

        if event_type == 'session':
            session_id = event.get('id')
            if not session_id:
                continue
            
            # Check if session already in DB
            session_obj = db.query(Session).filter_by(session_id=session_id).first()
            if not session_obj:
                try:
                    timestamp_str = event.get('timestamp', datetime.utcnow().isoformat())
                    started_at = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                except:
                    started_at = datetime.utcnow()
                
                session_obj = Session(
                    agent_id=agent_id,
                    session_id=session_id,
                    channel=event.get('channel', 'unknown'),
                    started_at=started_at,
                    status='active'
                )
                db.add(session_obj)
                db.commit()
                logger.debug(f'Created session: {session_id}')

        elif event_type == 'message' and session_id and session_obj:
            # Extract message details
            msg_data = event.get('message', {})
            usage = msg_data.get('usage', {}) if isinstance(msg_data, dict) else {}
            timestamp_str = event.get('timestamp', datetime.utcnow().isoformat())
            
            try:
                timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            except:
                timestamp = datetime.utcnow()
            
            model = msg_data.get('model') if isinstance(msg_data, dict) else None
            if not model:
                model = event.get('model') or None
            content_preview = _extract_content_preview(msg_data)

            input_tokens = _usage_value(usage, 'input', 'inputTokens', 'input_tokens')
            output_tokens = _usage_value(usage, 'output', 'outputTokens', 'output_tokens')
            cache_read_tokens = _usage_value(usage, 'cacheRead', 'cache_read', 'cacheReadTokens', 'cache_read_tokens')
            cache_write_tokens = _usage_value(usage, 'cacheWrite', 'cache_write', 'cacheWriteTokens', 'cache_write_tokens')
            total_tokens = _usage_value(
                usage,
                'totalTokens',
                'total_tokens',
                'total',
            )
            if total_tokens == 0:
                total_tokens = input_tokens + output_tokens + cache_read_tokens + cache_write_tokens
            
            delegated_agent_id = _extract_delegated_agent(msg_data)
            effective_agent_id = delegated_agent_id or agent_id

            # Ensure delegated agent exists for proper grouping
            if delegated_agent_id:
                delegated_agent = db.query(Agent).filter_by(agent_id=delegated_agent_id).first()
                if not delegated_agent:
                    delegated_agent = Agent(agent_id=delegated_agent_id, agent_name=delegated_agent_id)
                    db.add(delegated_agent)
                    db.flush()

            # Calculate cost based on token usage
            cost_data = calculate_message_cost(
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_read_tokens=cache_read_tokens,
                cache_write_tokens=cache_write_tokens,
            )

            # Check for duplicates (same session, same timestamp, same role)
            existing = db.query(Message).filter_by(
                session_id=session_id,
                timestamp=timestamp,
                role=msg_data.get('role', 'unknown'),
            ).first()
            
            if existing:
                logger.debug(f'Message already exists: {session_id}@{timestamp}')
                continue

            msg = Message(
                session_id=session_id,
                agent_id=effective_agent_id,
                timestamp=timestamp,
                role=msg_data.get('role', 'unknown'),
                model=model,
                content_preview=content_preview,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_read_tokens=cache_read_tokens,
                cache_write_tokens=cache_write_tokens,
                total_tokens=total_tokens,
                cost_input=cost_data['cost_input'],
                cost_output=cost_data['cost_output'],
                cost_cache_read=cost_data['cost_cache_read'],
                cost_cache_write=cost_data['cost_cache_write'],
                cost_total=cost_data['cost_total'],
                stop_reason=event.get('stopReason')
            )
            db.add(msg)

            # Update session totals
            if session_obj:
                session_obj.total_tokens = (session_obj.total_tokens or 0) + total_tokens
                session_obj.total_cost = (session_obj.total_cost or 0.0) + cost_data['cost_total']
                session_obj.message_count = (session_obj.message_count or 0) + 1
                session_obj.ended_at = timestamp

            if delegated_agent_id and cost_data['cost_total'] > 0:
                logger.info(
                    f'Attribution override: session {session_id} cost moved from {agent_id} to {delegated_agent_id}'
                )

    db.commit()

def full_scan():
    """Perform full scan of all agent sessions."""
    logger.info('=' * 60)
    logger.info('Starting full scan of OpenClaw sessions...')
    logger.info(f'Scanning: {AGENTS_DIR}')
    
    init_db()
    
    if not os.path.isdir(AGENTS_DIR):
        logger.error(f'Agents directory not found: {AGENTS_DIR}')
        return

    # Use openclaw.json as source of truth for active agents
    active_agent_ids = get_active_agent_ids()
    agent_count = 0
    for agent_dir in active_agent_ids:
        agent_path = os.path.join(AGENTS_DIR, agent_dir)
        if os.path.isdir(agent_path):
            try:
                process_agent_sessions(agent_dir)
                agent_count += 1
            except Exception as e:
                logger.error(f'Error processing agent {agent_dir}: {e}')

    # Prune DB agents no longer in openclaw.json
    db = SessionLocal()
    try:
        stale_agents = db.query(Agent).filter(Agent.agent_id.notin_(active_agent_ids)).all()
        for stale in stale_agents:
            logger.info(f'Removing stale agent from DB: {stale.agent_id}')
            db.delete(stale)
        db.commit()
    finally:
        db.close()

    logger.info(f'Full scan complete. Processed {agent_count} agents')
    logger.info('=' * 60)

def cleanup_old_data():
    """Delete data older than RETENTION_DAYS."""
    from datetime import datetime, timedelta
    from sqlalchemy import delete
    
    db = SessionLocal()
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=RETENTION_DAYS)
        
        # Delete old messages
        old_messages = db.query(Message).filter(Message.timestamp < cutoff_date).delete()
        
        # Delete old metrics
        cutoff_date_str = cutoff_date.strftime('%Y-%m-%d')
        old_metrics = db.query(DailyMetric).filter(DailyMetric.metric_date < cutoff_date_str).delete()
        
        db.commit()
        
        logger.info(f'Cleaned up old data: {old_messages} messages, {old_metrics} metrics')
    except Exception as e:
        logger.error(f'Error cleaning up old data: {e}')
        db.rollback()
    finally:
        db.close()

if __name__ == '__main__':
    full_scan()
