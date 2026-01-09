import sqlite3
import time
from datetime import datetime, timedelta

import os

# Vercel's only writable directory is /tmp
# Note: Data in /tmp is ephemeral and will be lost!
DB_NAME = '/tmp/bot_database.db' if os.environ.get('VERCEL') else 'bot_database.db'

def create_tables():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Users table: stores user info and subscription expiry
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            subscription_expiry TEXT,
            is_active INTEGER DEFAULT 0
        )
    ''')

    # Channels table: stores source and destination channels for each user
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            source_channel_id TEXT,
            dest_channel_id TEXT,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        )
    ''')
    
    # Payments table: stores payment requests
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            receipt_file_id TEXT,
            status TEXT DEFAULT 'pending', -- pending, approved, rejected
            created_at TEXT
        )
    ''')

    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def add_user(user_id, username, full_name):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO users (user_id, username, full_name) VALUES (?, ?, ?)', 
                   (user_id, username, full_name))
    conn.commit()
    conn.close()

def update_subscription(user_id, days=20):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    expiry_date = datetime.now() + timedelta(days=days)
    expiry_str = expiry_date.strftime('%Y-%m-%d %H:%M:%S')
    
    cursor.execute('UPDATE users SET subscription_expiry = ?, is_active = 1 WHERE user_id = ?', 
                   (expiry_str, user_id))
    conn.commit()
    conn.close()

def check_subscription(user_id):
    user = get_user(user_id)
    if not user or not user[3]: # user[3] is subscription_expiry
        return False
    
    expiry = datetime.strptime(user[3], '%Y-%m-%d %H:%M:%S')
    if datetime.now() < expiry:
        return True
    return False

def add_payment_request(user_id, file_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute('INSERT INTO payments (user_id, receipt_file_id, created_at) VALUES (?, ?, ?)', 
                   (user_id, file_id, created_at))
    payment_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return payment_id

def get_pending_payments():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM payments WHERE status = "pending"')
    payments = cursor.fetchall()
    conn.close()
    return payments

def update_payment_status(payment_id, status):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('UPDATE payments SET status = ? WHERE id = ?', (status, payment_id))
    conn.commit()
    conn.close()

def add_channel_config(user_id, source, dest):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Check if exists, update or insert
    cursor.execute('SELECT * FROM channels WHERE user_id = ?', (user_id,))
    if cursor.fetchone():
        cursor.execute('UPDATE channels SET source_channel_id = ?, dest_channel_id = ? WHERE user_id = ?', 
                       (source, dest, user_id))
    else:
        cursor.execute('INSERT INTO channels (user_id, source_channel_id, dest_channel_id) VALUES (?, ?, ?)', 
                       (user_id, source, dest))
    conn.commit()
    conn.close()

def get_user_channels(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT source_channel_id, dest_channel_id FROM channels WHERE user_id = ?', (user_id,))
    channels = cursor.fetchone()
    conn.close()
    return channels

def get_all_configs():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, source_channel_id, dest_channel_id FROM channels')
    configs = cursor.fetchall()
    conn.close()
    return configs

# Initialize
create_tables()
