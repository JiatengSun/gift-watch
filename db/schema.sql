CREATE TABLE IF NOT EXISTS gifts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts INTEGER NOT NULL,
  room_id INTEGER NOT NULL,
  uid INTEGER,
  uname TEXT,
  gift_id INTEGER,
  gift_name TEXT,
  num INTEGER DEFAULT 1,
  total_price INTEGER DEFAULT 0,
  raw_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_gifts_uname ON gifts(uname);
CREATE INDEX IF NOT EXISTS idx_gifts_gift  ON gifts(gift_name);
CREATE INDEX IF NOT EXISTS idx_gifts_ts    ON gifts(ts);
CREATE INDEX IF NOT EXISTS idx_gifts_room  ON gifts(room_id);
CREATE INDEX IF NOT EXISTS idx_gifts_room_ts ON gifts(room_id, ts);

CREATE TABLE IF NOT EXISTS danmaku_queue (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  message TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  not_before REAL NOT NULL,
  created_at REAL NOT NULL,
  sent_at REAL,
  last_error TEXT
);

CREATE INDEX IF NOT EXISTS idx_danmaku_queue_status_not_before
  ON danmaku_queue(status, not_before);

CREATE TABLE IF NOT EXISTS danmaku_queue_meta (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  last_sent_at REAL DEFAULT 0
);
