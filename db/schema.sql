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
