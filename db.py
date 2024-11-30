import sqlite3

DATABASE = 'slack.db'

def init_db():
    """
    Initialize the SQLite database with tables for messages and responses.
    """
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        # Create messages table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                author TEXT NOT NULL,
                message TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                bot BOOLEAN DEFAULT FALSE
            )
        ''')

        conn.commit()
