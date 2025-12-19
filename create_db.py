import os
import sqlite3
from werkzeug.security import generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# -------- USERS --------
cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    password TEXT,
    role TEXT
)
""")

# -------- INVOICES (HEADER) --------
cur.execute("""
CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_no TEXT,
    username TEXT,
    customer TEXT,
    customer_email TEXT,
    customer_phone TEXT,
    payment_mode TEXT,
    payment_status TEXT DEFAULT 'Pending',
    total REAL,
    date TEXT,
    status TEXT DEFAULT 'Pending'
)
""")

# -------- INVOICE ITEMS (BODY) --------
cur.execute("""
CREATE TABLE IF NOT EXISTS invoice_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER,
    item_name TEXT,
    qty INTEGER,
    rate REAL,
    amount REAL,
    FOREIGN KEY (invoice_id) REFERENCES invoices(id)
)
""")

# -------- DEFAULT ADMIN --------
cur.execute("""
INSERT OR IGNORE INTO users (username, password, role)
VALUES (?, ?, ?)
""", ("admin", generate_password_hash("admin123"), "admin"))

conn.commit()
conn.close()

print("✅ Database with invoice_items table created successfully")
