from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Index, Text, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker
from config import DATABASE_URL

engine = create_engine(DATABASE_URL, connect_args={'check_same_thread': False})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class Agent(Base):
    __tablename__ = 'agents'
    id = Column(Integer, primary_key=True)
    agent_id = Column(String(255), unique=True, index=True)
    agent_name = Column(String(255), nullable=True)
    default_model = Column(String(255), nullable=True)
    last_activity = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)

class Session(Base):
    __tablename__ = 'sessions'
    id = Column(Integer, primary_key=True)
    agent_id = Column(String(255), ForeignKey('agents.agent_id'), index=True)
    session_id = Column(String(255), unique=True, index=True)
    channel = Column(String(100), nullable=True)
    started_at = Column(DateTime, index=True)
    ended_at = Column(DateTime, nullable=True)
    total_tokens = Column(Integer, default=0)
    total_cost = Column(Float, default=0.0)
    message_count = Column(Integer, default=0)
    status = Column(String(50), default='active')  # active, completed, error
    created_at = Column(DateTime, default=datetime.utcnow)

class Message(Base):
    __tablename__ = 'messages'
    id = Column(Integer, primary_key=True)
    session_id = Column(String(255), ForeignKey('sessions.session_id'), index=True)
    agent_id = Column(String(255), index=True)
    timestamp = Column(DateTime, index=True)
    role = Column(String(50))  # user, assistant
    model = Column(String(255), nullable=True)
    content_preview = Column(Text, nullable=True)
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    cache_read_tokens = Column(Integer, default=0)
    cache_write_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    cost_input = Column(Float, default=0.0)
    cost_output = Column(Float, default=0.0)
    cost_cache_read = Column(Float, default=0.0)
    cost_cache_write = Column(Float, default=0.0)
    cost_total = Column(Float, default=0.0)
    stop_reason = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class DailyMetric(Base):
    __tablename__ = 'daily_metrics'
    id = Column(Integer, primary_key=True)
    metric_date = Column(String(10), index=True)  # YYYY-MM-DD
    agent_id = Column(String(255), index=True)
    model = Column(String(255), nullable=True)
    total_tokens = Column(Integer, default=0)
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    cache_read_tokens = Column(Integer, default=0)
    cache_write_tokens = Column(Integer, default=0)
    total_cost = Column(Float, default=0.0)
    cost_input = Column(Float, default=0.0)
    cost_output = Column(Float, default=0.0)
    cost_cache = Column(Float, default=0.0)
    message_count = Column(Integer, default=0)
    session_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

# Create indices
Index('idx_message_session_timestamp', Message.session_id, Message.timestamp)
Index('idx_daily_agent_model', DailyMetric.metric_date, DailyMetric.agent_id, DailyMetric.model)
Index('idx_session_started', Session.started_at)

def init_db():
    """Initialize database tables."""
    Base.metadata.create_all(bind=engine)

    inspector = inspect(engine)
    message_columns = {column['name'] for column in inspector.get_columns('messages')}

    with engine.begin() as connection:
        if 'content_preview' not in message_columns:
            connection.execute(text('ALTER TABLE messages ADD COLUMN content_preview TEXT'))

    print('✓ Database initialized')
