"""SQLite: отдельное соединение на операцию, параметризованные запросы."""
import sqlite3
from contextlib import closing
from pathlib import Path


class Database:
    def __init__(self, path):
        self.path = Path(path)

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as conn, conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL, text TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT
                    (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            )''')

    def connect(self):
        conn = sqlite3.connect(self.path, timeout=5)
        conn.row_factory = sqlite3.Row
        return conn

    def list_messages(self, limit=100):
        with closing(self.connect()) as conn:
            rows = conn.execute(
                'SELECT * FROM messages ORDER BY id DESC LIMIT ?', (limit,)
            ).fetchall()
            return [dict(row) for row in reversed(rows)]

    def insert(self, name, text):
        with closing(self.connect()) as conn, conn:
            cursor = conn.execute(
                'INSERT INTO messages(name, text) VALUES (?, ?)', (name, text)
            )
            return dict(conn.execute('SELECT * FROM messages WHERE id = ?',
                                     (cursor.lastrowid,)).fetchone())

    def get(self, message_id):
        with closing(self.connect()) as conn:
            row = conn.execute('SELECT * FROM messages WHERE id = ?',
                               (message_id,)).fetchone()
            return dict(row) if row else None
