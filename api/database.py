import sqlite3, os

DB_PATH = os.getenv("DB_PATH", "/data/yupoo.db")

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_conn()
    c = conn.cursor()

    c.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id          TEXT PRIMARY KEY,
        email       TEXT UNIQUE NOT NULL,
        name        TEXT,
        avatar      TEXT,
        credits     INTEGER DEFAULT 0,
        created_at  INTEGER DEFAULT (strftime('%s','now'))
    );

    CREATE TABLE IF NOT EXISTS transactions (
        id          TEXT PRIMARY KEY,
        user_id     TEXT NOT NULL,
        type        TEXT NOT NULL,
        amount      INTEGER NOT NULL,
        description TEXT,
        stripe_id   TEXT,
        created_at  INTEGER DEFAULT (strftime('%s','now')),
        FOREIGN KEY (user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS jobs (
        id              TEXT PRIMARY KEY,
        user_id         TEXT NOT NULL,
        yupoo_url       TEXT NOT NULL,
        album_name      TEXT,
        status          TEXT DEFAULT 'pending',
        destination     TEXT DEFAULT 'drive',
        drive_folder_id TEXT,
        total_images    INTEGER DEFAULT 0,
        processed       INTEGER DEFAULT 0,
        failed          INTEGER DEFAULT 0,
        credits_used    INTEGER DEFAULT 0,
        log             TEXT DEFAULT '',
        created_at      INTEGER DEFAULT (strftime('%s','now')),
        updated_at      INTEGER DEFAULT (strftime('%s','now')),
        FOREIGN KEY (user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS stripe_webhooks (
        id          TEXT PRIMARY KEY,
        event_type  TEXT,
        payload     TEXT,
        processed   INTEGER DEFAULT 0,
        created_at  INTEGER DEFAULT (strftime('%s','now'))
    );
    """)
    
    # Migrações automáticas
    try:
        c.execute("ALTER TABLE jobs ADD COLUMN job_type TEXT DEFAULT 'album'")
    except sqlite3.OperationalError:
        pass # Coluna já existe

    try:
        c.execute("ALTER TABLE jobs ADD COLUMN album_name TEXT")
    except sqlite3.OperationalError:
        pass # Coluna já existe

    conn.commit()
    conn.close()
