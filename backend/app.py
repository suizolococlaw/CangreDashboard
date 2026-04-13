"""Flask REST API server for CangreDashboard."""

from flask import Flask, jsonify, request
from flask_cors import CORS
from datetime import datetime, timedelta
from sqlalchemy import func, desc
from schema import init_db, SessionLocal, Agent, Session, Message, DailyMetric
from aggregator import full_scan, cleanup_old_data
from cost_analyzer import (
    aggregate_daily_costs, get_cost_summary, get_cost_by_agent, 
    get_cost_by_model, get_cost_trend, estimate_burn_rate, get_cost_by_prompt
)
from config import FLASK_HOST, FLASK_PORT, DEBUG, validate_config
import threading
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

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
        
        # Agent list with stats
        agents = db.query(Agent).all()
        agent_stats = []
        for agent in agents:
            agent_tokens = db.query(func.sum(Message.total_tokens)).filter_by(agent_id=agent.agent_id).scalar() or 0
            agent_cost = db.query(func.sum(Message.cost_total)).filter_by(agent_id=agent.agent_id).scalar() or 0.0
            agent_stats.append({
                'agent_id': agent.agent_id,
                'name': agent.agent_name,
                'total_tokens': agent_tokens,
                'total_cost': round(agent_cost, 4),
                'last_activity': agent.last_activity.isoformat() if agent.last_activity else None
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


@app.route('/api/cost/by-prompt', methods=['GET'])
def cost_by_prompt():
    """Get per-prompt cost rows and repeated-prompt hotspots."""
    limit = int(request.args.get('limit', 25))
    agent_id = request.args.get('agent_id')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    db = SessionLocal()
    try:
        payload = get_cost_by_prompt(
            db,
            limit=limit,
            agent_id=agent_id,
            start_date=start_date,
            end_date=end_date,
        )
        return jsonify(payload)
    finally:
        db.close()

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
