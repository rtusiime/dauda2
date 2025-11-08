"""
Database abstraction layer
Supports both SQLite (local dev) and PostgreSQL (production)
"""

import os
from typing import Optional
from contextlib import contextmanager

# Check which database to use
DATABASE_URL = os.getenv('DATABASE_URL')
USE_POSTGRES = DATABASE_URL is not None and DATABASE_URL.startswith('postgres')

if USE_POSTGRES:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    print("Using PostgreSQL database")
else:
    import sqlite3
    print("Using SQLite database")


class Database:
    """Database connection manager"""

    def __init__(self):
        self.db_url = DATABASE_URL
        self.use_postgres = USE_POSTGRES

        if not self.use_postgres:
            self.db_path = os.getenv('DATABASE_PATH', 'calendar_sync.db')

    @contextmanager
    def get_connection(self):
        """Get a database connection (context manager)"""
        if self.use_postgres:
            conn = psycopg2.connect(self.db_url)
            try:
                yield conn
            finally:
                conn.close()
        else:
            conn = sqlite3.connect(self.db_path)
            try:
                yield conn
            finally:
                conn.close()

    def get_cursor(self, conn):
        """Get appropriate cursor for the database type"""
        if self.use_postgres:
            return conn.cursor(cursor_factory=RealDictCursor)
        else:
            conn.row_factory = sqlite3.Row
            return conn.cursor()

    def init_db(self):
        """Initialize database tables"""
        with self.get_connection() as conn:
            c = self.get_cursor(conn)

            if self.use_postgres:
                # PostgreSQL schema
                c.execute('''
                    CREATE TABLE IF NOT EXISTS bookings (
                        id SERIAL PRIMARY KEY,
                        platform TEXT NOT NULL,
                        checkin TEXT NOT NULL,
                        checkout TEXT NOT NULL,
                        property_id TEXT,
                        guest_name TEXT,
                        confirmation_code TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        blocked_on_other_platform BOOLEAN DEFAULT FALSE,
                        error_message TEXT
                    )
                ''')

                c.execute('''
                    CREATE TABLE IF NOT EXISTS block_tasks (
                        id SERIAL PRIMARY KEY,
                        booking_id INTEGER REFERENCES bookings(id),
                        target_platform TEXT NOT NULL,
                        status TEXT DEFAULT 'pending',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        completed_at TIMESTAMP,
                        error_message TEXT
                    )
                ''')
            else:
                # SQLite schema
                c.execute('''
                    CREATE TABLE IF NOT EXISTS bookings (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        platform TEXT NOT NULL,
                        checkin TEXT NOT NULL,
                        checkout TEXT NOT NULL,
                        property_id TEXT,
                        guest_name TEXT,
                        confirmation_code TEXT,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        blocked_on_other_platform INTEGER DEFAULT 0,
                        error_message TEXT
                    )
                ''')

                c.execute('''
                    CREATE TABLE IF NOT EXISTS block_tasks (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        booking_id INTEGER,
                        target_platform TEXT NOT NULL,
                        status TEXT DEFAULT 'pending',
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        completed_at TEXT,
                        error_message TEXT,
                        FOREIGN KEY (booking_id) REFERENCES bookings(id)
                    )
                ''')

            conn.commit()
            print("Database initialized successfully")


# Global database instance
db = Database()
