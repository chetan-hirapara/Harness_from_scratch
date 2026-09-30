"""
Customer Support Refund Agent - 15 Real Tools

Non-RAG system: Real refund logic, calculations, decision-making.

Tools:
1-3:   Conversation & Intake
4-6:   Lookup & Validation
7-9:   Assessment
10-12: Calculation & Decision
13-15: Execution & Response
"""

import sqlite3
import json
import re
import uuid
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List

import llm_client


DB_PATH = Path.cwd() / "data" / "customer_support.db"


# ============================================================================
# CONVERSATION & INTAKE STAGE (Tools 1-3)
# ============================================================================

async def tool_extract_customer_intent(message: str = "", **kwargs) -> Dict[str, Any]:
    """
    Tool 1: Parse customer message to extract intent
    
    Detects: refund request, order status, question, etc.
    """
    message_lower = message.lower()
    
    intent = "unknown"
    if any(word in message_lower for word in ["refund", "return", "money back", "reimburse"]):
        intent = "refund_request"
    elif any(word in message_lower for word in ["order", "status", "where", "tracking"]):
        intent = "order_status"
    elif any(word in message_lower for word in ["damaged", "broken", "defective", "not work"]):
        intent = "damage_claim"
    elif any(word in message_lower for word in ["wrong", "incorrect", "mistake"]):
        intent = "wrong_item"
    elif any(word in message_lower for word in ["changed mind", "don't want", "don't like"]):
        intent = "change_of_mind"
    
    method = "keyword"
    allowed = {"refund_request", "order_status", "damage_claim", "wrong_item", "change_of_mind", "unknown"}
    llm_result = await llm_client.chat_json(
        system=(
            "You classify a customer support message into exactly one intent. "
            "Reply ONLY with JSON {\"intent\": <label>} where label is one of: "
            "refund_request, order_status, damage_claim, wrong_item, change_of_mind, unknown."
        ),
        user=message,
    )
    if llm_result and llm_result.get("intent") in allowed:
        intent = llm_result["intent"]
        method = "llm"
    
    return {
        "intent": intent,
        "message": message,
        "keywords": [w for w in message.split() if len(w) > 3],
        "method": method
    }


async def tool_extract_order_reference(message: str = "", **kwargs) -> Dict[str, Any]:
    """
    Tool 2: Extract order ID from customer message
    
    Looks for: "ORD-XXX", "order number", "order #", etc.
    """
    # Find patterns like ORD-001-MOBILE or order numbers
    patterns = [
        r'ORD-\d+-[A-Z]+',
        r'order\s*(?:number|#|id)?[\s:]*([A-Z0-9\-]+)',
    ]
    
    order_id = None
    for pattern in patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            order_id = match.group(0) if pattern == patterns[0] else match.group(1)
            break
    
    return {
        "order_id": order_id,
        "found": order_id is not None,
        "message": message
    }


async def tool_maintain_conversation_state(
    conversation_id: str = "",
    customer_id: str = "",
    order_id: str = "",
    messages: List[Dict] = None,
    new_message: str = "",
    **kwargs
) -> Dict[str, Any]:
    """
    Tool 3: Maintain conversation state across turns
    
    Tracks: customer_id, order_id, conversation history, context
    """
    if messages is None:
        messages = []
    
    # Add new message to history
    messages.append({
        "role": "customer",
        "text": new_message,
        "timestamp": datetime.now().isoformat()
    })
    
    return {
        "conversation_id": conversation_id or str(uuid.uuid4()),
        "customer_id": customer_id,
        "order_id": order_id,
        "messages": messages,
        "message_count": len(messages),
        "last_message": messages[-1] if messages else None
    }


# ============================================================================
# LOOKUP & VALIDATION STAGE (Tools 4-6)
# ============================================================================

async def tool_lookup_order_from_db(order_id: str = "", **kwargs) -> Dict[str, Any]:
    """
    Tool 4: Fetch order details from SQLite database
    
    Returns: all order info (product, price, date, shipping, tax)
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return {
                "found": False,
                "order_id": order_id,
                "error": f"Order {order_id} not found"
            }
        
        order = dict(row)
        return {
            "found": True,
            "order_id": order['order_id'],
            "customer_id": order['customer_id'],
            "customer_name": order['customer_name'],
            "product_name": order['product_name'],
            "product_price": order['product_price'],
            "shipping_cost": order['shipping_cost'],
            "tax_amount": order['tax_amount'],
            "order_date": order['order_date'],
            "status": order['status']
        }
    except Exception as e:
        return {
            "found": False,
            "order_id": order_id,
            "error": str(e)
        }


async def tool_validate_return_window(
    lookup_order_from_db: Dict = None,
    return_window_days: int = 30,
    **kwargs
) -> Dict[str, Any]:
    """
    Tool 5: Check if order is within return window
    
    Window: 30 days from order_date
    """
    try:
        if not lookup_order_from_db or not lookup_order_from_db.get("found"):
            return {
                "within_window": False,
                "error": "Order not found"
            }
        
        order_date = lookup_order_from_db.get("order_date", "")
        order_dt = datetime.fromisoformat(order_date)
        days_since_order = (datetime.now() - order_dt).days
        within_window = days_since_order <= return_window_days
        
        return {
            "order_date": order_date,
            "days_since_order": days_since_order,
            "return_window_days": return_window_days,
            "within_window": within_window,
            "window_status": "OPEN" if within_window else "CLOSED",
            "days_remaining": max(0, return_window_days - days_since_order)
        }
    except Exception as e:
        return {
            "error": str(e),
            "within_window": False
        }


async def tool_check_previous_refund(lookup_order_from_db: Dict = None, **kwargs) -> Dict[str, Any]:
    """
    Tool 6: Check if this order has been refunded already
    
    Prevents double refunds
    """
    try:
        if not lookup_order_from_db or not lookup_order_from_db.get("found"):
            return {
                "previously_refunded": False,
                "order_id": "",
                "error": "Order not found"
            }
        
        order_id = lookup_order_from_db.get("order_id", "")
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM refunds WHERE order_id = ?", (order_id,))
        refund = cursor.fetchone()
        conn.close()
        
        if refund:
            return {
                "previously_refunded": True,
                "order_id": order_id,
                "refund_id": refund[0],
                "status": refund[7],  # status column
                "message": f"This order was already refunded with ID {refund[0]}"
            }
        
        return {
            "previously_refunded": False,
            "order_id": order_id,
            "message": "No previous refund found"
        }
    except Exception as e:
        return {
            "error": str(e),
            "previously_refunded": False
        }


# ============================================================================
# ASSESSMENT STAGE (Tools 7-9)
# ============================================================================

async def tool_assess_item_condition(
    message: str = "",
    **kwargs
) -> Dict[str, Any]:
    """
    Tool 7: Assess item condition from customer message
    
    Categories: unopened, used_good, used_poor, damaged, defective
    """
    message_lower = message.lower()
    
    condition = "unknown"
    is_defective = False
    
    if any(word in message_lower for word in ["unopened", "unused", "new", "sealed", "never opened"]):
        condition = "unopened"
    elif any(word in message_lower for word in ["used but good", "wore once", "gently used", "good shape"]):
        condition = "used_good"
    elif any(word in message_lower for word in ["worn", "used", "dirty"]):
        condition = "used_poor"
    elif any(word in message_lower for word in ["damaged", "broken", "cracked", "defective", "not work", "doesn't work", "doesn't function"]):
        condition = "damaged"
        is_defective = True
    
    method = "keyword"
    allowed = {"unopened", "used_good", "used_poor", "damaged", "defective", "unknown"}
    llm_result = await llm_client.chat_json(
        system=(
            "You assess a returned item's condition from the customer's message. "
            "Reply ONLY with JSON {\"condition\": <label>} where label is one of: "
            "unopened, used_good, used_poor, damaged, defective, unknown."
        ),
        user=message,
    )
    if llm_result and llm_result.get("condition") in allowed:
        condition = llm_result["condition"]
        is_defective = condition in ("damaged", "defective")
        method = "llm"
    
    return {
        "condition": condition,
        "is_defective": is_defective,
        "message": message,
        "unopened": condition == "unopened",
        "method": method
    }


async def tool_extract_refund_request_details(
    message: str = "",
    **kwargs
) -> Dict[str, Any]:
    """
    Tool 8: Extract details about why customer wants refund
    
    Reasons: damaged, defective, changed_mind, wrong_item, wrong_size, etc.
    """
    message_lower = message.lower()
    
    reason = "unknown"
    is_customer_fault = True  # Default: customer pays return shipping
    
    if any(word in message_lower for word in ["damaged", "broken", "defective", "not work"]):
        reason = "damaged_or_defective"
        is_customer_fault = False  # We pay return shipping
    elif any(word in message_lower for word in ["wrong", "incorrect", "mistake"]):
        reason = "wrong_item"
        is_customer_fault = False  # Our mistake, we pay return shipping
    elif any(word in message_lower for word in ["changed mind", "don't want", "don't like", "don't need"]):
        reason = "changed_mind"
        is_customer_fault = True  # Customer pays
    elif any(word in message_lower for word in ["wrong size", "too small", "too big"]):
        reason = "wrong_size"
        is_customer_fault = True  # Customer pays
    else:
        reason = "other"
    
    # Fault-to-reason mapping drives return-shipping deduction; keep it deterministic.
    fault_by_reason = {
        "damaged_or_defective": False,
        "wrong_item": False,
        "changed_mind": True,
        "wrong_size": True,
        "other": True,
        "unknown": True,
    }
    llm_result = await llm_client.chat_json(
        system=(
            "You extract why a customer wants a refund. "
            "Reply ONLY with JSON {\"reason\": <label>} where label is one of: "
            "damaged_or_defective, wrong_item, changed_mind, wrong_size, other, unknown."
        ),
        user=message,
    )
    if llm_result and llm_result.get("reason") in fault_by_reason:
        reason = llm_result["reason"]
        is_customer_fault = fault_by_reason[reason]
    
    return {
        "reason": reason,
        "is_customer_fault": is_customer_fault,
        "deduct_return_shipping": is_customer_fault,
        "message": message
    }


async def tool_check_idempotency(
    lookup_order_from_db: Dict = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Tool 9: Generate idempotency key to prevent double refunds
    
    Key = hash(order_id + customer_id)
    Unique in DB to prevent duplicate refunds
    """
    if not lookup_order_from_db or not lookup_order_from_db.get("found"):
        return {
            "error": "Order not found",
            "is_duplicate": False
        }
    
    order_id = lookup_order_from_db.get("order_id", "")
    customer_id = lookup_order_from_db.get("customer_id", "")
    
    # Generate idempotency key
    combined = f"{order_id}:{customer_id}"
    idempotency_key = hashlib.sha256(combined.encode()).hexdigest()[:16]
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("SELECT refund_id FROM refunds WHERE idempotency_key = ?", (idempotency_key,))
        existing = cursor.fetchone()
        conn.close()
        
        if existing:
            return {
                "is_duplicate": True,
                "idempotency_key": idempotency_key,
                "existing_refund_id": existing[0],
                "message": "Duplicate refund request detected"
            }
        
        return {
            "is_duplicate": False,
            "idempotency_key": idempotency_key,
            "order_id": order_id,
            "customer_id": customer_id
        }
    except Exception as e:
        return {
            "error": str(e),
            "idempotency_key": idempotency_key,
            "is_duplicate": False
        }


# ============================================================================
# CALCULATION & DECISION STAGE (Tools 10-12)
# ============================================================================

async def tool_calculate_refund_amount(
    lookup_order_from_db: Dict = None,
    extract_refund_request_details: Dict = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Tool 10: Calculate exact refund amount
    
    Logic:
    - Base refund: product_price
    - Deduct shipping: always
    - Deduct tax: always
    - Deduct return shipping: only if customer's fault
    """
    if not lookup_order_from_db or not lookup_order_from_db.get("found"):
        return {"error": "Order not found", "refund_amount": 0}
    
    product_price = lookup_order_from_db.get("product_price", 0)
    shipping_cost = lookup_order_from_db.get("shipping_cost", 0)
    tax_amount = lookup_order_from_db.get("tax_amount", 0)
    
    is_customer_fault = extract_refund_request_details.get("is_customer_fault", True) if extract_refund_request_details else True
    
    # Assume return shipping = outgoing shipping (for simplicity)
    return_shipping = shipping_cost if is_customer_fault else 0
    
    refund_amount = product_price - shipping_cost - tax_amount - return_shipping
    refund_amount = max(0, refund_amount)  # Can't be negative
    
    breakdown = {
        "product_price": product_price,
        "deduct_shipping": -shipping_cost,
        "deduct_tax": -tax_amount,
        "deduct_return_shipping": -return_shipping,
        "total_refund": refund_amount
    }
    
    return {
        "refund_amount": refund_amount,
        "breakdown": breakdown,
        "is_customer_fault": is_customer_fault,
        "return_shipping_deducted": return_shipping > 0
    }


async def tool_apply_policy_rules(
    validate_return_window: Dict = None,
    check_previous_refund: Dict = None,
    calculate_refund_amount: Dict = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Tool 11: Apply business policy rules
    
    Rules:
    - Outside return window → REJECT
    - Already refunded → REJECT
    - Else → APPROVE
    
    Note: Condition doesn't block refund, but noted for audit
    """
    within_window = validate_return_window.get("within_window", False) if validate_return_window else False
    previously_refunded = check_previous_refund.get("previously_refunded", False) if check_previous_refund else False
    refund_amount = calculate_refund_amount.get("refund_amount", 0) if calculate_refund_amount else 0
    
    decision = "APPROVE"
    reason = "Meets all criteria"
    
    if previously_refunded:
        decision = "REJECT"
        reason = "Order already refunded"
    elif not within_window:
        decision = "REJECT"
        reason = "Outside 30-day return window"
    elif refund_amount <= 0 and not previously_refunded:  # Only reject if no prior refund and amount is 0
        decision = "REJECT"
        reason = "Refund amount is zero or negative"
    
    return {
        "decision": decision,
        "reason": reason,
        "within_window": within_window,
        "policies_met": decision == "APPROVE"
    }


async def tool_make_refund_decision(
    lookup_order_from_db: Dict = None,
    calculate_refund_amount: Dict = None,
    apply_policy_rules: Dict = None,
    check_idempotency: Dict = None,
    assess_item_condition: Dict = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Tool 12: Make final refund decision + create refund record
    
    Creates refund in DB with status APPROVED or REJECTED
    """
    # Extract data from dependencies
    if not lookup_order_from_db or not lookup_order_from_db.get("found"):
        return {"error": "Order not found", "created": False}
    
    order_id = lookup_order_from_db.get("order_id", "")
    customer_id = lookup_order_from_db.get("customer_id", "")
    
    refund_amount = calculate_refund_amount.get("refund_amount", 0) if calculate_refund_amount else 0
    decision_from_rules = apply_policy_rules.get("decision", "APPROVE") if apply_policy_rules else "APPROVE"
    reason = apply_policy_rules.get("reason", "") if apply_policy_rules else ""
    breakdown = calculate_refund_amount.get("breakdown", {}) if calculate_refund_amount else {}
    idempotency_key = check_idempotency.get("idempotency_key", "") if check_idempotency else ""
    is_defective = assess_item_condition.get("is_defective", False) if assess_item_condition else False
    
    refund_id = f"REF-{str(uuid.uuid4())[:8].upper()}"
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO refunds 
            (refund_id, order_id, customer_id, refund_amount, is_defective, 
             calculation_breakdown, status, idempotency_key, approval_timestamp, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            refund_id,
            order_id,
            customer_id,
            refund_amount,
            1 if is_defective else 0,
            json.dumps(breakdown),
            decision_from_rules,  # APPROVED or REJECTED
            idempotency_key,
            datetime.now().isoformat(),
            datetime.now().isoformat()
        ))
        
        conn.commit()
        conn.close()
        
        return {
            "refund_id": refund_id,
            "order_id": order_id,
            "decision": decision_from_rules,
            "reason": reason,
            "refund_amount": refund_amount,
            "breakdown": breakdown,
            "status": "APPROVED",
            "created": True
        }
    except sqlite3.IntegrityError as e:
        if "UNIQUE constraint failed: refunds.order_id" in str(e):
            # Refund already exists - fetch it instead of creating duplicate
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM refunds WHERE order_id = ?", (order_id,))
            existing = cursor.fetchone()
            conn.close()
            
            if existing:
                return {
                    "refund_id": existing[0],
                    "order_id": order_id,
                    "decision": existing[7],  # status
                    "reason": "Refund already exists for this order",
                    "refund_amount": existing[3],
                    "breakdown": json.loads(existing[5]) if existing[5] else {},
                    "status": existing[7],
                    "created": False,
                    "already_exists": True
                }
        elif "UNIQUE constraint failed: refunds.idempotency_key" in str(e):
            # Same idempotency key - fetch existing refund
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM refunds WHERE idempotency_key = ?", (idempotency_key,))
            existing = cursor.fetchone()
            conn.close()
            
            if existing:
                return {
                    "refund_id": existing[0],
                    "order_id": order_id,
                    "decision": existing[7],  # status
                    "reason": "Duplicate refund request (idempotency key already exists)",
                    "refund_amount": existing[3],
                    "breakdown": json.loads(existing[5]) if existing[5] else {},
                    "status": existing[7],
                    "created": False,
                    "duplicate": True
                }
        
        return {
            "error": str(e),
            "created": False
        }
    except Exception as e:
        return {
            "error": str(e),
            "created": False
        }


# ============================================================================
# EXECUTION & RESPONSE STAGE (Tools 13-15)
# ============================================================================

async def tool_process_refund_in_db(
    make_refund_decision: Dict = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Tool 13: Update refund status in database
    
    Ensures status is set correctly
    """
    if not make_refund_decision or not make_refund_decision.get("created", False):
        # Refund wasn't created (maybe it already existed), just return existing info
        refund_id = make_refund_decision.get("refund_id", "") if make_refund_decision else ""
        status = make_refund_decision.get("status", "APPROVED") if make_refund_decision else "APPROVED"
        return {
            "refund_id": refund_id,
            "status": status,
            "updated": False,
            "message": "Refund already exists"
        }
    
    refund_id = make_refund_decision.get("refund_id", "")
    status = make_refund_decision.get("status", "APPROVED")
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute(
            "UPDATE refunds SET status = ? WHERE refund_id = ?",
            (status, refund_id)
        )
        
        conn.commit()
        conn.close()
        
        return {
            "refund_id": refund_id,
            "status": status,
            "updated": True,
            "message": f"Refund {refund_id} status updated to {status}"
        }
    except Exception as e:
        return {
            "error": str(e),
            "updated": False
        }


async def tool_initiate_payment(
    process_refund_in_db: Dict = None,
    make_refund_decision: Dict = None,
    lookup_order_from_db: Dict = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Tool 14: Initiate refund payment (mock)
    
    In real system: call payment processor (Stripe, PayPal, etc)
    Here: simulate payment processing + update status to INITIATED
    """
    refund_id = make_refund_decision.get("refund_id", "") if make_refund_decision else ""
    refund_amount = make_refund_decision.get("refund_amount", 0) if make_refund_decision else 0
    customer_id = lookup_order_from_db.get("customer_id", "") if lookup_order_from_db else ""
    
    try:
        # Mock payment processing
        import asyncio
        await asyncio.sleep(0.1)  # Simulate payment latency
        
        payment_id = f"PAY-{str(uuid.uuid4())[:8].upper()}"
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute(
            "UPDATE refunds SET status = 'INITIATED', initiated_timestamp = ? WHERE refund_id = ?",
            (datetime.now().isoformat(), refund_id)
        )
        
        conn.commit()
        conn.close()
        
        return {
            "refund_id": refund_id,
            "payment_id": payment_id,
            "amount": refund_amount,
            "customer_id": customer_id,
            "status": "INITIATED",
            "message": f"Refund of ${refund_amount:.2f} initiated (Payment ID: {payment_id})",
            "success": True
        }
    except Exception as e:
        return {
            "error": str(e),
            "success": False
        }


async def tool_generate_customer_response(
    make_refund_decision: Dict = None,
    lookup_order_from_db: Dict = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Tool 15: Generate human-friendly response to customer
    
    LLM-like tone, explains decision + next steps
    """
    decision = make_refund_decision.get("decision", "PENDING") if make_refund_decision else "PENDING"
    refund_amount = make_refund_decision.get("refund_amount", 0) if make_refund_decision else 0
    reason = make_refund_decision.get("reason", "") if make_refund_decision else ""
    refund_id = make_refund_decision.get("refund_id", "") if make_refund_decision else ""
    product_name = lookup_order_from_db.get("product_name", "your item") if lookup_order_from_db else "your item"
    
    if decision == "APPROVED" or decision == "APPROVE":
        response = f"""Great news! Your refund has been approved! 🎉

Here are the details:
- **Refund ID:** {refund_id}
- **Refund Amount:** ${refund_amount:.2f}
- **Product:** {product_name}

The refund has been initiated and should appear in your account within 3-5 business days.

Thank you for shopping with us, and we're sorry the {product_name} didn't work out!"""
    
    elif decision == "REJECTED" or decision == "REJECT":
        response = f"""Unfortunately, we cannot process a refund for your request.

Reason: {reason}

However, if you believe this decision is incorrect or if you have additional information, please reply to this conversation and we'll review your case.

We appreciate your business!"""
    
    else:
        response = f"""We received your refund request for your order.

Decision: {decision}
Reason: {reason}

Thank you for contacting us!"""
    
    method = "template"
    facts = (
        f"decision: {decision}\n"
        f"product: {product_name}\n"
        f"refund_id: {refund_id}\n"
        f"refund_amount_usd: {refund_amount:.2f}\n"
        f"reason: {reason}"
    )
    llm_text = await llm_client.chat_text(
        system=(
            "You are a friendly e-commerce customer support agent. Write a concise, warm "
            "reply to the customer about their refund. Use ONLY the facts provided; never "
            "invent or alter the refund ID, amount, or decision. If approved, mention the "
            "refund ID, exact amount, and a 3-5 business day timeline. If rejected, be "
            "empathetic, state the reason, and offer to review the case. Reply with plain "
            "message text only."
        ),
        user=facts,
    )
    if llm_text:
        response = llm_text
        method = "llm"
    
    return {
        "decision": decision,
        "refund_amount": refund_amount,
        "response": response,
        "method": method,
        "generated_at": datetime.now().isoformat()
    }


# ============================================================================
# Tool Registry
# ============================================================================

TOOLS = {
    # Conversation & Intake
    "extract_customer_intent": tool_extract_customer_intent,
    "extract_order_reference": tool_extract_order_reference,
    "maintain_conversation_state": tool_maintain_conversation_state,
    
    # Lookup & Validation
    "lookup_order_from_db": tool_lookup_order_from_db,
    "validate_return_window": tool_validate_return_window,
    "check_previous_refund": tool_check_previous_refund,
    
    # Assessment
    "assess_item_condition": tool_assess_item_condition,
    "extract_refund_request_details": tool_extract_refund_request_details,
    "check_idempotency": tool_check_idempotency,
    
    # Calculation & Decision
    "calculate_refund_amount": tool_calculate_refund_amount,
    "apply_policy_rules": tool_apply_policy_rules,
    "make_refund_decision": tool_make_refund_decision,
    
    # Execution & Response
    "process_refund_in_db": tool_process_refund_in_db,
    "initiate_payment": tool_initiate_payment,
    "generate_customer_response": tool_generate_customer_response,
}

print(f"✓ Loaded {len(TOOLS)} tools")
