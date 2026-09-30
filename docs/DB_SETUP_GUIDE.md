# Database Setup Guide

## Quick Start

### Initialize/Reset Database
```bash
python3 setup_db.py
```

This will:
1. ✓ Delete any existing `customer_support.db`
2. ✓ Create fresh schema (orders, refunds, conversations tables)
3. ✓ Populate 4 test orders
4. ✓ Display summary

### Clear Database Only
```bash
python3 setup_db.py --clear-only
```

Deletes the database file without reinitializing.

---

## Database Schema

### Orders Table
```sql
CREATE TABLE orders (
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
```

### Refunds Table
```sql
CREATE TABLE refunds (
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
```

### Conversations Table
```sql
CREATE TABLE conversations (
    conversation_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    order_id TEXT,
    messages TEXT NOT NULL,
    created_at TEXT NOT NULL
)
```

---

## Test Orders (Auto-Populated)

| Order ID | Customer | Product | Price | Days Ago | Expected Result |
|----------|----------|---------|-------|----------|-----------------|
| ORD-001-MOBILE | Alice Johnson | Samsung Galaxy S24 | $800.00 | 15 | ✓ APPROVED ($680) |
| ORD-002-SHOES | Bob Smith | Nike Running Shoes | $150.00 | 40 | ✗ REJECTED (outside 30d) |
| ORD-003-SHIRT | Carol Davis | Cotton T-Shirt | $30.00 | 23 | ✓ APPROVED ($19) |
| ORD-004-LAPTOP | David Wilson | Lenovo ThinkPad | $1200.00 | 8 | ✓ APPROVED ($1030, defective) |

---

## Refund Calculations

### Mobile ($800 product, within 30 days, customer fault)
```
Product Price:      $800.00
- Shipping:         - $20.00
- Tax:              - $80.00
- Return Shipping:  - $20.00  (customer pays)
─────────────────────────────
= Refund:            $680.00 ✓ APPROVED
```

### Shoes ($150 product, 40 days, outside return window)
```
Days Since Order: 40 days
Return Window:    30 days
─────────────────────────
Result:           $0.00 ✗ REJECTED
```

### Shirt ($30 product, within 30 days)
```
Product Price:      $30.00
- Shipping:         - $8.00
- Tax:              - $3.00
- Return Shipping:  - $8.00
─────────────────────────
= Refund:            $19.00 ✓ APPROVED
```

### Laptop ($1200 product, within 30 days, defective by us)
```
Product Price:      $1200.00
- Shipping:         - $50.00
- Tax:              - $120.00
- Return Shipping:  $0.00    (we pay, it's our fault)
─────────────────────────────
= Refund:            $1030.00 ✓ APPROVED
```

---

## Idempotency Testing

The refund agent uses **SHA256(order_id:customer_id)** as the idempotency key.

### Same Request Twice
```
Request 1 (15:30:00): Customer asks for refund
  → Agent creates refund REF-ABC123
  → Stores idempotency_key: sha256(ORD-001:CUST-001)
  
Request 2 (15:35:00): Customer repeats (network retry)
  → Agent recomputes same idempotency_key
  → Database UNIQUE constraint prevents duplicate insert
  → Returns existing REF-ABC123 (no double charge)
```

---

## Usage With Agent

### Step 1: Reset Database
```bash
python3 setup_db.py
```

### Step 2: Run Agent
```bash
python3 support_agent_main.py
```

Example conversation:
```
Customer: "I want to return my Samsung Galaxy S24"
Agent: [Looks up ORD-001-MOBILE, runs 15 tools, calculates $680 refund]
Agent: "Your refund of $680.00 has been approved. REF-001-APPROVED"

Customer: "Can you repeat that?"
Agent: [Same conversation, but returns same REF-001-APPROVED (idempotent)]
```

### Step 3: Reset and Run Tests Again
```bash
python3 setup_db.py
python3 support_agent_main.py
```

---

## Database Inspection

### View all orders
```python
import sqlite3
conn = sqlite3.connect('customer_support.db')
cursor = conn.cursor()
cursor.execute('SELECT * FROM orders')
for row in cursor.fetchall():
    print(row)
```

### View all refunds
```python
cursor.execute('SELECT refund_id, order_id, refund_amount, status FROM refunds')
for row in cursor.fetchall():
    print(row)
```

### Check idempotency
```python
cursor.execute('''
    SELECT idempotency_key, COUNT(*) 
    FROM refunds 
    GROUP BY idempotency_key
''')
for row in cursor.fetchall():
    print(f"Key: {row[0]}, Count: {row[1]}")
```

---

## Troubleshooting

### Database locked error
- Kill any running agents: `pkill -f support_agent_main.py`
- Reset: `python3 setup_db.py`

### Import errors
- Ensure Python 3.8+: `python3 --version`
- Check dependencies: `pip install sqlite3` (built-in, usually)

### Test data not appearing
- Verify: `python3 setup_db.py` output shows "✓ Populated 4 test orders"
- Check file permissions: `ls -la customer_support.db`

---

## Files

- **setup_db.py** — Database initialization script
- **customer_support.db** — SQLite database (created by setup_db.py)
- **support_agent_main.py** — Main agent orchestrator
- **support_agent_tools.py** — 15 tool implementations
- **support_agent_spec.yaml** — DAG specification
- **support_agent_orchestrator.py** — Multi-turn conversation engine

---

## Summary

| Command | Purpose |
|---------|---------|
| `python3 setup_db.py` | Initialize fresh DB with 4 test orders |
| `python3 setup_db.py --clear-only` | Delete DB only |
| `python3 support_agent_main.py` | Run agent on initialized DB |

**Remember:** Always run `python3 setup_db.py` before testing to ensure clean state.
