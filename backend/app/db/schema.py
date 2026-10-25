"""建表与轻量迁移。"""
from ..core.database import db

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS channels (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  grp TEXT DEFAULT 'default',
  vendor TEXT DEFAULT '',
  base_url TEXT NOT NULL,
  api_key TEXT DEFAULT '',
  protocol TEXT DEFAULT 'openai',
  enabled INTEGER DEFAULT 1,
  timeout_ms INTEGER DEFAULT 60000,
  weight INTEGER DEFAULT 1,
  max_concurrency INTEGER DEFAULT 5,
  max_retries INTEGER DEFAULT 1,
  cooldown_sec INTEGER DEFAULT 60,
  http_proxy TEXT DEFAULT '',
  extra_headers TEXT DEFAULT '{}',
  retry_status_codes TEXT DEFAULT '[429,500,502,503,504]',
  silent_degrade INTEGER DEFAULT 0,
  model_whitelist TEXT DEFAULT '',
  model_blacklist TEXT DEFAULT '',
  cb_error_threshold REAL DEFAULT 0,
  cb_window_sec INTEGER DEFAULT 0,
  cb_freeze_sec INTEGER DEFAULT 0,
  paid INTEGER DEFAULT 0,
  today_requests INTEGER DEFAULT 0,
  today_failures INTEGER DEFAULT 0,
  created_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS models (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  channel_id INTEGER NOT NULL,
  upstream_model TEXT NOT NULL,
  alias TEXT DEFAULT '',
  vendor_tag TEXT DEFAULT '',
  emoji TEXT DEFAULT '',
  grp TEXT DEFAULT 'default',
  enabled INTEGER DEFAULT 1,
  remark TEXT DEFAULT '',
  skip_health INTEGER DEFAULT 0,
  prefer_group TEXT DEFAULT '',
  sort_order INTEGER DEFAULT 0,
  status TEXT DEFAULT 'unknown',
  last_http_status INTEGER,
  latency_ms INTEGER,
  last_check_time TEXT DEFAULT '',
  UNIQUE(channel_id, upstream_model)
);

CREATE TABLE IF NOT EXISTS api_keys (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  key TEXT UNIQUE NOT NULL,
  name TEXT DEFAULT '',
  tag TEXT DEFAULT '',
  enabled INTEGER DEFAULT 1,
  expires_at TEXT DEFAULT '',
  quota_requests INTEGER DEFAULT 0,
  quota_total_tokens INTEGER DEFAULT 0,
  quota_input_tokens INTEGER DEFAULT 0,
  quota_output_tokens INTEGER DEFAULT 0,
  period TEXT DEFAULT 'none',
  rps INTEGER DEFAULT 0,
  model_whitelist TEXT DEFAULT '',
  model_blacklist TEXT DEFAULT '',
  ip_whitelist TEXT DEFAULT '',
  alert_threshold INTEGER DEFAULT 80,
  used_requests INTEGER DEFAULT 0,
  used_input_tokens INTEGER DEFAULT 0,
  used_output_tokens INTEGER DEFAULT 0,
  last_used_at TEXT DEFAULT '',
  period_anchor TEXT DEFAULT '',
  created_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT DEFAULT '',
  request_type TEXT DEFAULT 'forward',
  protocol TEXT DEFAULT 'openai',
  key_name TEXT DEFAULT '',
  model TEXT DEFAULT '',
  vendor_tag TEXT DEFAULT '',
  source_ip TEXT DEFAULT '',
  channel TEXT DEFAULT '',
  latency_ms INTEGER DEFAULT 0,
  prompt_tokens INTEGER DEFAULT 0,
  completion_tokens INTEGER DEFAULT 0,
  http_status INTEGER DEFAULT 0,
  status TEXT DEFAULT 'success',
  error TEXT DEFAULT '',
  request_payload TEXT DEFAULT '',
  response_payload TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_logs_ts ON logs(ts);
CREATE INDEX IF NOT EXISTS idx_logs_status ON logs(status);
CREATE INDEX IF NOT EXISTS idx_logs_model ON logs(model);

CREATE TABLE IF NOT EXISTS routing_rules (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  priority INTEGER DEFAULT 0,
  match_type TEXT DEFAULT 'model',
  match_value TEXT DEFAULT '',
  target_group TEXT DEFAULT '',
  enabled INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS proxy_rules (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT DEFAULT '',
  path_prefix TEXT DEFAULT '',
  target_url TEXT DEFAULT '',
  api_key TEXT DEFAULT '',
  vendor_tag TEXT DEFAULT '',
  enabled INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS model_blacklist (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  model TEXT UNIQUE NOT NULL,
  reason TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS auto_rules (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  keyword TEXT NOT NULL,
  model_name TEXT NOT NULL,
  priority INTEGER DEFAULT 0,
  enabled INTEGER DEFAULT 1,
  created_at TEXT DEFAULT ''
);
"""

COLS = {
    "channels": {
        "cb_error_threshold": "REAL DEFAULT 0",
        "cb_window_sec": "INTEGER DEFAULT 0",
        "cb_freeze_sec": "INTEGER DEFAULT 0",
        "today_requests": "INTEGER DEFAULT 0",
        "today_failures": "INTEGER DEFAULT 0",
        "grp": "TEXT DEFAULT 'default'",
        "vendor": "TEXT DEFAULT ''",
        "paid": "INTEGER DEFAULT 0",
    },
    "models": {
        "prefer_group": "TEXT DEFAULT ''",
        "grp": "TEXT DEFAULT 'default'",
        "emoji": "TEXT DEFAULT ''",
        "remark": "TEXT DEFAULT ''",
        "sort_order": "INTEGER DEFAULT 0",
    },
    "api_keys": {
        "tag": "TEXT DEFAULT ''",
        "alert_threshold": "INTEGER DEFAULT 80",
        "period_anchor": "TEXT DEFAULT ''",
    },
    "logs": {
        "protocol": "TEXT DEFAULT 'openai'",
        "vendor_tag": "TEXT DEFAULT ''",
        "http_status": "INTEGER DEFAULT 0",
    },
}


async def init_db():
    await db.executescript(SCHEMA)
    # 轻量迁移：缺列则补
    for table, cols in COLS.items():
        rows = await db.fetchall(f"PRAGMA table_info({table})")
        existing = {r["name"] for r in rows}
        for col, ddl in cols.items():
            if col not in existing:
                await db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
