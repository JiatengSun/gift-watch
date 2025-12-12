CREATE TABLE IF NOT EXISTS danmaku_queue (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  room_id INTEGER NOT NULL,
  message TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  not_before REAL NOT NULL,
  created_at REAL NOT NULL,
  sent_at REAL,
  last_error TEXT
);

CREATE INDEX IF NOT EXISTS idx_danmaku_queue_room_status_not_before
  ON danmaku_queue(room_id, status, not_before);

CREATE TABLE IF NOT EXISTS danmaku_queue_meta (
  room_id INTEGER PRIMARY KEY,
  last_sent_at REAL DEFAULT 0
);
