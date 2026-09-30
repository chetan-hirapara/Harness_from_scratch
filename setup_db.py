#!/usr/bin/env python3
"""
setup_db.py - Initialize or reset the customer support refund agent database

This script:
1. Deletes the existing database (if any)
2. Creates a fresh SQLite database with schema
3. Populates 4 test orders
4. Creates empty refunds and conversations tables

Usage:
    python setup_db.py                  # Create fresh DB with test data
    python setup_db.py --reset          # Same as above
    python setup_db.py --clear-only     # Delete DB only
"""

import sqlite3
import os
import sys
from datetime import datetime, timedelta
import json

DB_PATH = "./data/customer_support.db"
os.makedirs("./data", exist_ok=True)

def delete_db():
    """Delete existing database"""
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print(f"✓ Deleted existing database: {DB_PATH}")
    else:
        print(f"ℹ No existing database found at {DB_PATH}")

def create_schema(conn):
    """Create database schema"""
    cursor = conn.cursor()
    
    # Orders table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            order_id TEXT PRIMARY KEY,
            customer_id TEXT NOT NULL,
            customer_name TEXT NOT NULL,
            product_name TEXT NOT NULL,
            product_price REAL NOT NULL,
            shipping_cost REAL NOT NULL,
            tax_amount REAL NOT NULL,
            order_date TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    ''')
    print("✓ Created orders table")
    
    # Refunds table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS refunds (
            refund_id TEXT PRIMARY KEY,
            order_id TEXT NOT NULL UNIQUE,
            customer_id TEXT NOT NULL,
            refund_amount REAL NOT NULL,
            is_defective BOOLEAN NOT NULL,
            calculation_breakdown TEXT NOT NULL,
            status TEXT NOT NULL,
            idempotency_key TEXT NOT NULL UNIQUE,
            approval_timestamp TEXT,
            initiated_timestamp TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (order_id) REFERENCES orders(order_id)
        )
    ''')
    print("✓ Created refunds table")
    
    # Conversations table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS conversations (
            conversation_id TEXT PRIMARY KEY,
            customer_id TEXT NOT NULL,
            order_id TEXT,
            messages TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    ''')
    print("✓ Created conversations table")
    
    conn.commit()

def populate_test_data(conn):
    """Populate test orders"""
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    
    test_orders = [
        {
            'order_id': 'ORD-001-MOBILE',
            'customer_id': 'CUST-001',
            'customer_name': 'Alice Johnson',
            'product_name': 'Samsung Galaxy S24',
            'product_price': 800.00,
            'shipping_cost': 20.00,
            'tax_amount': 80.00,
            'order_date': (datetime.now() - timedelta(days=15)).date().isoformat(),
            'status': 'DELIVERED',
            'created_at': now
        },
        {
            'order_id': 'ORD-002-SHOES',
            'customer_id': 'CUST-002',
            'customer_name': 'Bob Smith',
            'product_name': 'Nike Running Shoes',
            'product_price': 150.00,
            'shipping_cost': 10.00,
            'tax_amount': 16.00,
            'order_date': (datetime.now() - timedelta(days=40)).date().isoformat(),
            'status': 'DELIVERED',
            'created_at': now
        },
        {
            'order_id': 'ORD-003-SHIRT',
            'customer_id': 'CUST-003',
            'customer_name': 'Carol Davis',
            'product_name': 'Cotton T-Shirt',
            'product_price': 30.00,
            'shipping_cost': 8.00,
            'tax_amount': 3.00,
            'order_date': (datetime.now() - timedelta(days=23)).date().isoformat(),
            'status': 'DELIVERED',
            'created_at': now
        },
        {
            'order_id': 'ORD-004-LAPTOP',
            'customer_id': 'CUST-004',
            'customer_name': 'David Wilson',
            'product_name': 'Lenovo ThinkPad',
            'product_price': 1200.00,
            'shipping_cost': 50.00,
            'tax_amount': 120.00,
            'order_date': (datetime.now() - timedelta(days=8)).date().isoformat(),
            'status': 'DELIVERED',
            'created_at': now
        }
    ]
    
    for order in test_orders:
        cursor.execute('''
            INSERT INTO orders (
                order_id, customer_id, customer_name, product_name,
                product_price, shipping_cost, tax_amount, order_date, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            order['order_id'], order['customer_id'], order['customer_name'],
            order['product_name'], order['product_price'], order['shipping_cost'],
            order['tax_amount'], order['order_date'], order['status'], order['created_at']
        ))
    
    conn.commit()
    print(f"✓ Populated {len(test_orders)} test orders:")
    for order in test_orders:
        days_ago = (datetime.now() - datetime.fromisoformat(order['order_date'])).days
        print(f"  - {order['order_id']}: {order['product_name']} ({days_ago} days ago)")

def verify_data(conn):
    """Verify database is populated correctly"""
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM orders')
    order_count = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM refunds')
    refund_count = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM conversations')
    conv_count = cursor.fetchone()[0]
    
    print(f"\n📊 Database Status:")
    print(f"  Orders: {order_count}")
    print(f"  Refunds: {refund_count}")
    print(f"  Conversations: {conv_count}")

def main():
    """Main setup function"""
    print("🔧 Customer Support Refund Agent - Database Setup\n")
    
    # Parse arguments
    reset_only = '--clear-only' in sys.argv
    
    if reset_only:
        delete_db()
        print("✓ Database cleared. Run without --clear-only to initialize.")
        sys.exit(0)
    
    # Normal setup: delete old, create new
    delete_db()
    
    # Connect to database
    conn = sqlite3.connect(DB_PATH)
    print(f"✓ Connected to {DB_PATH}\n")
    
    # Create schema
    create_schema(conn)
    print()
    
    # Populate test data
    populate_test_data(conn)
    print()
    
    # Verify
    verify_data(conn)
    
    conn.close()
    print(f"\n✅ Database setup complete!")
    print(f"   Location: {os.path.abspath(DB_PATH)}")
    print(f"\n📝 Ready to use with support_agent_main.py")

if __name__ == '__main__':
    main()
