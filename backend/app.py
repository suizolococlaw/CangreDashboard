"""Flask REST API server for CangreDashboard."""

from flask import Flask, jsonify, request, Response
import csv
import io
import json
import os
from flask_cors import CORS
from datetime import datetime, timedelta
from sqlalchemy import func, desc
from schema import init_db, SessionLocal, Agent, Session, Message, DailyMetric
from aggregator import full_scan, cleanup_old_data
from cost_analyzer import (
    aggregate_daily_costs, get_cost_summary, get_cost_by_agent, 
    get_cost_by_model, get_cost_trend, estimate_burn_rate, get_cost_by_prompt
)
from config import FLASK_HOST, FLASK_PORT, DEBUG, validate_config, MONTHLY_BUDGET, COPILOT_START_DATE, SETUP_MONTHS, get_active_agent_ids
import threading
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

BASELINE_FILE = os.path.expanduser('~/.openclaw/cangre_baseline.json')
MILESTONES_FILE = os.path.expanduser('~/.openclaw/cangre_milestones.json')
RESOLUTIONS_FILE = os.path.expanduser('~/.openclaw/cangre_rec_resolutions.json')

# Initialize on startup
@app.before_request
def startup():
    if not hasattr(app, '_initialized'):
        try:
            validate_config()
            init_db()
            # Run scan in background thread so API starts immediately
            threading.Thread(target=full_scan, daemon=True).start()
            app._initialized = True
        except Exception as e:
            logger.error(f'Startup error: {e}')

# Health check
@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'service': 'cangre-dashboard'})

# ============================================================================
# OVERVIEW ENDPOINTS
# ============================================================================

@app.route('/api/overview', methods=['GET'])
def overview():
    """Get today's overview stats."""
    db = SessionLocal()
    try:
        today = datetime.utcnow().strftime('%Y-%m-%d')
        
        # Today's metrics from aggregation
        today_metrics = db.query(DailyMetric).filter_by(metric_date=today).all()
        total_tokens_today = sum(m.total_tokens for m in today_metrics)
        total_cost_today = sum(m.total_cost for m in today_metrics)
        session_count_today = sum(m.session_count for m in today_metrics)
        
        # Yesterday for comparison
        yesterday = (datetime.utcnow() - timedelta(days=1)).strftime('%Y-%m-%d')
        yesterday_metrics = db.query(DailyMetric).filter_by(metric_date=yesterday).all()
        total_cost_yesterday = sum(m.total_cost for m in yesterday_metrics)
        
        # Active sessions
        active_sessions = db.query(Session).filter_by(status='active').count()
        
        # Agent list with stats — all agents currently defined in openclaw.json
        # cangrejo is always first (primary agent), rest alphabetical
        active_ids = get_active_agent_ids()
        db_agents = {a.agent_id: a for a in db.query(Agent).all()}
        agent_stats = []
        for agent_id in sorted(active_ids, key=lambda x: (0 if x == 'cangrejo' else 1, x)):
            agent = db_agents.get(agent_id)
            if agent:
                agent_tokens = db.query(func.sum(Message.total_tokens)).filter_by(agent_id=agent_id).scalar() or 0
                agent_cost = db.query(func.sum(Message.cost_total)).filter_by(agent_id=agent_id).scalar() or 0.0
                last_activity = agent.last_activity.isoformat() if agent.last_activity else None
            else:
                agent_tokens = 0
                agent_cost = 0.0
                last_activity = None
            agent_stats.append({
                'agent_id': agent_id,
                'name': agent.agent_name if agent else agent_id,
                'total_tokens': agent_tokens,
                'total_cost': round(agent_cost, 4),
                'last_activity': last_activity
            })
        
        cost_vs_yesterday = round(total_cost_today - total_cost_yesterday, 4) if total_cost_yesterday > 0 else 0
        cost_change_pct = (cost_vs_yesterday / total_cost_yesterday * 100) if total_cost_yesterday > 0 else 0
        
        return jsonify({
            'date': today,
            'total_tokens_today': total_tokens_today,
            'total_cost_today': round(total_cost_today, 4),
            'cost_vs_yesterday': cost_vs_yesterday,
            'cost_change_pct': round(cost_change_pct, 2),
            'active_sessions': active_sessions,
            'session_count_today': session_count_today,
            'agents': agent_stats,
            'timestamp': datetime.utcnow().isoformat()
        })
    finally:
        db.close()

@app.route('/api/sessions', methods=['GET'])
def get_sessions():
    """Get all sessions with filters."""
    agent_id = request.args.get('agent_id')
    status = request.args.get('status', 'all')
    limit = int(request.args.get('limit', 50))
    
    db = SessionLocal()
    try:
        query = db.query(Session)
        if agent_id:
            query = query.filter_by(agent_id=agent_id)
        if status != 'all':
            query = query.filter_by(status=status)
        
        sessions = query.order_by(desc(Session.started_at)).limit(limit).all()
        
        return jsonify([{
            'session_id': s.session_id,
            'agent_id': s.agent_id,
            'channel': s.channel,
            'started_at': s.started_at.isoformat(),
            'ended_at': s.ended_at.isoformat() if s.ended_at else None,
            'total_tokens': s.total_tokens,
            'total_cost': round(s.total_cost or 0.0, 4),
            'message_count': s.message_count,
            'status': s.status
        } for s in sessions])
    finally:
        db.close()

# ============================================================================
# TIMELINE ENDPOINTS
# ============================================================================

@app.route('/api/timeline', methods=['GET'])
def get_timeline():
    """Get chronological execution timeline."""
    limit = int(request.args.get('limit', 100))
    agent_id = request.args.get('agent_id')
    
    db = SessionLocal()
    try:
        query = db.query(Message)
        if agent_id:
            query = query.filter_by(agent_id=agent_id)
        
        messages = query.order_by(desc(Message.timestamp)).limit(limit).all()
        
        return jsonify([{
            'timestamp': m.timestamp.isoformat(),
            'agent_id': m.agent_id,
            'session_id': m.session_id,
            'role': m.role,
            'model': m.model,
            'tokens': m.total_tokens,
            'cost': round(m.cost_total, 6),
            'input_tokens': m.input_tokens,
            'output_tokens': m.output_tokens,
        } for m in reversed(messages)])
    finally:
        db.close()

# ============================================================================
# COST & METRICS ENDPOINTS
# ============================================================================

@app.route('/api/metrics/daily', methods=['GET'])
def metrics_daily():
    """Get daily metrics for last N days."""
    days = int(request.args.get('days', 7))
    
    db = SessionLocal()
    try:
        trend = get_cost_trend(db, days=days)
        return jsonify(trend)
    finally:
        db.close()

@app.route('/api/metrics/summary', methods=['GET'])
def metrics_summary():
    """Get overall cost summary."""
    db = SessionLocal()
    try:
        summary = get_cost_summary(db)
        return jsonify(summary)
    finally:
        db.close()

@app.route('/api/cost/by-agent', methods=['GET'])
def cost_by_agent():
    """Get cost breakdown by agent."""
    db = SessionLocal()
    try:
        breakdown = get_cost_by_agent(db)
        return jsonify(breakdown)
    finally:
        db.close()

@app.route('/api/cost/by-model', methods=['GET'])
def cost_by_model():
    """Get cost breakdown by model."""
    db = SessionLocal()
    try:
        breakdown = get_cost_by_model(db)
        return jsonify(breakdown)
    finally:
        db.close()

@app.route('/api/cost/burn-rate', methods=['GET'])
def cost_burn_rate():
    """Get current burn rate estimate."""
    window_hours = int(request.args.get('window_hours', 24))
    
    db = SessionLocal()
    try:
        burn = estimate_burn_rate(db, window_hours=window_hours)
        return jsonify(burn)
    finally:
        db.close()


@app.route('/api/cost/month', methods=['GET'])
def cost_this_month():
    """Return current-month spend vs budget cap (filtered to GitHub Copilot era)."""
    db = SessionLocal()
    try:
        import calendar
        now = datetime.utcnow()
        ym = now.strftime('%Y-%m')

        start_of_month = datetime(now.year, now.month, 1)
        copilot_start = datetime.fromisoformat(COPILOT_START_DATE)
        billing_start = max(start_of_month, copilot_start)

        total_spend = db.query(func.sum(Message.cost_total)).filter(
            func.strftime('%Y-%m', Message.timestamp) == ym,
            Message.timestamp >= billing_start,
        ).scalar() or 0.0

        days_in_month = calendar.monthrange(now.year, now.month)[1]
        end_of_month = datetime(now.year, now.month, days_in_month)
        billing_period_days = (end_of_month - billing_start).days + 1
        days_elapsed = max(1, (now - billing_start).days + 1)
        days_remaining = max(0, days_in_month - now.day)
        daily_avg = total_spend / days_elapsed if days_elapsed > 0 else 0.0
        projected = daily_avg * billing_period_days
        pct_used = (total_spend / MONTHLY_BUDGET * 100) if MONTHLY_BUDGET > 0 else 0.0
        if pct_used < 70:
            status = 'ok'
        elif pct_used < 90:
            status = 'warning'
        else:
            status = 'critical'
        return jsonify({
            'month': ym,
            'current_spend': round(total_spend, 4),
            'monthly_budget': MONTHLY_BUDGET,
            'pct_used': round(pct_used, 2),
            'days_elapsed': days_elapsed,
            'days_remaining': days_remaining,
            'days_in_month': days_in_month,
            'billing_period_days': billing_period_days,
            'projected_month_end': round(projected, 4),
            'daily_avg': round(daily_avg, 6),
            'budget_status': status,
        })
    finally:
        db.close()


@app.route('/api/cost/periods', methods=['GET'])
def cost_periods():
    """Return per-month spend history from Copilot start date."""
    db = SessionLocal()
    try:
        copilot_start = datetime.fromisoformat(COPILOT_START_DATE)
        results = db.query(
            func.strftime('%Y-%m', Message.timestamp).label('month'),
            func.sum(Message.cost_total).label('spend'),
        ).filter(
            Message.timestamp >= copilot_start,
        ).group_by(
            func.strftime('%Y-%m', Message.timestamp)
        ).order_by('month').all()

        periods = []
        for r in results:
            spend = round(r.spend or 0.0, 4)
            pct = round(spend / MONTHLY_BUDGET * 100, 1) if MONTHLY_BUDGET > 0 else 0.0
            deviation = round(spend - MONTHLY_BUDGET, 4)
            is_setup = r.month in SETUP_MONTHS
            periods.append({
                'month': r.month,
                'spend': spend,
                'budget': MONTHLY_BUDGET,
                'pct_used': pct,
                'deviation': deviation,
                'is_setup': is_setup,
                'note': 'setup/learning' if is_setup else None,
            })
        return jsonify(periods)
    finally:
        db.close()


@app.route('/api/cost/by-prompt', methods=['GET'])
def cost_by_prompt():
    """Get per-prompt cost rows and repeated-prompt hotspots."""
    limit = int(request.args.get('limit', 25))
    agent_id = request.args.get('agent_id')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    repeated_only = request.args.get('repeated_only', 'false').lower() == 'true'
    top_n = int(request.args.get('top_n', 10))

    db = SessionLocal()
    try:
        payload = get_cost_by_prompt(
            db,
            limit=limit,
            agent_id=agent_id,
            start_date=start_date,
            end_date=end_date,
            repeated_only=repeated_only,
            top_n_recommendations=top_n,
        )
        # Enrich repeated_prompts with resolution_status
        resolutions = {}
        if os.path.exists(RESOLUTIONS_FILE):
            with open(RESOLUTIONS_FILE, 'r') as f:
                resolutions = json.load(f)
        now = datetime.utcnow()
        from cost_analyzer import _normalize_prompt_key
        for item in payload.get('repeated_prompts', []):
            key = _normalize_prompt_key(item['prompt_preview'])
            last_seen_str = item.get('last_seen')
            days_since = 9999
            if last_seen_str:
                try:
                    last_seen_dt = datetime.fromisoformat(last_seen_str)
                    days_since = (now - last_seen_dt).total_seconds() / 86400
                except ValueError:
                    pass
            ack = resolutions.get(key)
            if ack:
                item['acknowledged_at'] = ack['acknowledged_at']
                try:
                    ack_dt = datetime.fromisoformat(ack['acknowledged_at'])
                    last_seen_dt = datetime.fromisoformat(last_seen_str) if last_seen_str else None
                    if last_seen_dt and last_seen_dt > ack_dt:
                        item['resolution_status'] = 'regressed'
                    elif days_since >= 7:
                        item['resolution_status'] = 'resolved'
                    else:
                        item['resolution_status'] = 'watching'
                except (ValueError, UnboundLocalError):
                    item['resolution_status'] = 'watching'
            else:
                item['acknowledged_at'] = None
                item['resolution_status'] = 'resolved' if days_since >= 7 else 'active'
        return jsonify(payload)
    finally:
        db.close()

@app.route('/api/export/prompt-costs.csv', methods=['GET'])
def export_prompt_costs_csv():
    """Export prompt cost data as a CSV download. mode=all (default) or mode=repeated."""
    limit = int(request.args.get('limit', 1000))
    agent_id = request.args.get('agent_id')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    mode = request.args.get('mode', 'all')  # 'all' or 'repeated'

    db = SessionLocal()
    try:
        payload = get_cost_by_prompt(db, limit=limit, agent_id=agent_id,
                                     start_date=start_date, end_date=end_date,
                                     top_n_recommendations=1000)
    finally:
        db.close()

    output = io.StringIO()
    if mode == 'repeated':
        fieldnames = ['prompt_preview', 'occurrences', 'total_cost', 'avg_cost', 'max_cost',
                      'potential_savings', 'merge_opportunity_score', 'total_tokens', 'agents', 'sessions']
        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        for row in payload['repeated_prompts']:
            row_out = dict(row)
            row_out['agents'] = '|'.join(row_out.get('agents') or [])
            row_out['sessions'] = '|'.join(row_out.get('sessions') or [])
            writer.writerow(row_out)
        suffix = 'repeated'
    else:
        fieldnames = ['timestamp', 'agent_id', 'session_id', 'model', 'prompt_preview',
                      'cost', 'tokens', 'input_tokens', 'output_tokens',
                      'cache_read_tokens', 'cache_write_tokens']
        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        for row in payload['prompts']:
            writer.writerow(row)
        suffix = 'all'

    filename = f"prompt-costs-{suffix}-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.csv"
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )


@app.route('/api/agents', methods=['GET'])
def get_agents():
    """Get all agents with stats."""
    db = SessionLocal()
    try:
        agents = db.query(Agent).all()
        
        stats = []
        for agent in agents:
            total_tokens = db.query(func.sum(Message.total_tokens)).filter_by(agent_id=agent.agent_id).scalar() or 0
            total_cost = db.query(func.sum(Message.cost_total)).filter_by(agent_id=agent.agent_id).scalar() or 0.0
            session_count = db.query(Session).filter_by(agent_id=agent.agent_id).count()
            
            stats.append({
                'agent_id': agent.agent_id,
                'name': agent.agent_name,
                'total_tokens': total_tokens,
                'total_cost': round(total_cost, 4),
                'session_count': session_count,
                'last_activity': agent.last_activity.isoformat() if agent.last_activity else None
            })
        
        return jsonify(stats)
    finally:
        db.close()

# ============================================================================
# ADMIN ENDPOINTS
# ============================================================================

@app.route('/api/admin/rescan', methods=['POST'])
def admin_rescan():
    """Trigger a full rescan of OpenClaw logs."""
    threading.Thread(target=full_scan, daemon=True).start()
    return jsonify({'status': 'rescan started', 'timestamp': datetime.utcnow().isoformat()})


@app.route('/api/sessions/<session_id_param>/prompts', methods=['GET'])
def session_prompts(session_id_param):
    """Get all prompt turns for a specific session."""
    db = SessionLocal()
    try:
        rows = db.query(Message).filter_by(session_id=session_id_param).order_by(
            Message.timestamp.asc(), Message.id.asc()).all()
        last_user_prompt = None
        turns = []
        for row in rows:
            preview = (row.content_preview or '').strip()
            if row.role == 'user':
                last_user_prompt = preview
                continue
            if row.role != 'assistant' or (row.cost_total or 0) <= 0:
                continue
            turns.append({
                'timestamp': row.timestamp.isoformat() if row.timestamp else None,
                'agent_id': row.agent_id,
                'session_id': row.session_id,
                'model': row.model or 'unknown',
                'prompt_preview': last_user_prompt or preview or '(No prompt preview captured)',
                'cost': round(row.cost_total or 0.0, 6),
                'tokens': row.total_tokens or 0,
                'input_tokens': row.input_tokens or 0,
                'output_tokens': row.output_tokens or 0,
                'cache_read_tokens': row.cache_read_tokens or 0,
                'cache_write_tokens': row.cache_write_tokens or 0,
            })
        return jsonify({'session_id': session_id_param, 'turns': turns})
    finally:
        db.close()


@app.route('/api/cost/baseline', methods=['GET'])
def get_baseline():
    """Retrieve saved cost baseline."""
    if not os.path.exists(BASELINE_FILE):
        return jsonify({'baseline': None})
    with open(BASELINE_FILE, 'r') as f:
        return jsonify({'baseline': json.load(f)})


@app.route('/api/cost/baseline', methods=['POST'])
def capture_baseline():
    """Capture current cost summary as baseline snapshot."""
    db = SessionLocal()
    try:
        payload = get_cost_by_prompt(db, limit=1000, top_n_recommendations=100)
    finally:
        db.close()
    snapshot = {
        'captured_at': datetime.utcnow().isoformat(),
        'summary': payload['summary'],
    }
    os.makedirs(os.path.dirname(BASELINE_FILE), exist_ok=True)
    with open(BASELINE_FILE, 'w') as f:
        json.dump(snapshot, f, indent=2)
    return jsonify({'status': 'baseline saved', 'snapshot': snapshot})


# ============================================================================
# MILESTONES
# ============================================================================

def _load_milestones():
    if not os.path.exists(MILESTONES_FILE):
        return []
    with open(MILESTONES_FILE, 'r') as f:
        return json.load(f)

def _save_milestones(milestones):
    os.makedirs(os.path.dirname(MILESTONES_FILE), exist_ok=True)
    with open(MILESTONES_FILE, 'w') as f:
        json.dump(milestones, f, indent=2)


@app.route('/api/milestones', methods=['GET'])
def get_milestones():
    return jsonify(_load_milestones())


@app.route('/api/milestones', methods=['POST'])
def create_milestone():
    body = request.get_json(silent=True) or {}
    name = (body.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'name is required'}), 400
    db = SessionLocal()
    try:
        payload = get_cost_by_prompt(db, limit=1000, top_n_recommendations=100)
    finally:
        db.close()
    s = payload['summary']
    milestone = {
        'id': f"m_{int(time.time())}",
        'name': name,
        'note': (body.get('note') or '').strip() or None,
        'created_at': datetime.utcnow().isoformat(),
        'snapshot': {
            'repeated_prompt_spend': s.get('repeated_prompt_spend', 0),
            'repeated_prompt_turns': s.get('repeated_prompt_turns', 0),
            'potential_savings': s.get('potential_savings', 0),
            'merge_opportunity_score': s.get('merge_opportunity_score', 0),
            'billable_prompts': s.get('billable_prompts', 0),
        },
    }
    milestones = _load_milestones()
    milestones.append(milestone)
    _save_milestones(milestones)
    return jsonify(milestone), 201


@app.route('/api/milestones/<milestone_id>', methods=['DELETE'])
def delete_milestone(milestone_id):
    milestones = _load_milestones()
    remaining = [m for m in milestones if m['id'] != milestone_id]
    if len(remaining) == len(milestones):
        return jsonify({'error': 'not found'}), 404
    _save_milestones(remaining)
    return jsonify({'status': 'deleted'})


# ============================================================================
# RECOMMENDATION RESOLUTION
# ============================================================================

@app.route('/api/recommendations/acknowledge', methods=['POST'])
def acknowledge_recommendation():
    body = request.get_json(silent=True) or {}
    prompt_key = (body.get('prompt_key') or '').strip()
    if not prompt_key:
        return jsonify({'error': 'prompt_key is required'}), 400
    resolutions = {}
    if os.path.exists(RESOLUTIONS_FILE):
        with open(RESOLUTIONS_FILE, 'r') as f:
            resolutions = json.load(f)
    now_iso = datetime.utcnow().isoformat()
    resolutions[prompt_key] = {'acknowledged_at': now_iso}
    os.makedirs(os.path.dirname(RESOLUTIONS_FILE), exist_ok=True)
    with open(RESOLUTIONS_FILE, 'w') as f:
        json.dump(resolutions, f, indent=2)
    return jsonify({'status': 'ok', 'prompt_key': prompt_key, 'acknowledged_at': now_iso})


@app.route('/api/admin/cleanup', methods=['POST'])
def admin_cleanup():
    """Trigger cleanup of old data."""
    threading.Thread(target=cleanup_old_data, daemon=True).start()
    return jsonify({'status': 'cleanup started', 'timestamp': datetime.utcnow().isoformat()})

@app.route('/api/admin/aggregate-costs', methods=['POST'])
def admin_aggregate_costs():
    """Trigger cost aggregation."""
    db = SessionLocal()
    try:
        aggregate_daily_costs(db)
        return jsonify({'status': 'aggregation complete', 'timestamp': datetime.utcnow().isoformat()})
    finally:
        db.close()

if __name__ == '__main__':
    logger.info(f'Starting CangreDashboard Backend on {FLASK_HOST}:{FLASK_PORT}')
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=DEBUG)
