"""
Customer Support Refund Agent - Multi-Turn Conversation Tests

Test Scenarios:
1. Samsung Galaxy S24 (mobile) - Within window, changed mind, unopened
2. Nike Shoes - Outside window, never wore
3. Cotton T-Shirt - Within window, wrong size, tried on
4. Lenovo Laptop - Within window, DEFECTIVE (broken on arrival)

Each scenario shows:
- Multi-turn conversation flow
- Idempotency (no double refunds)
- Real calculation logic
- Full trajectory capture
"""

import asyncio
import json
import os
from datetime import datetime, timedelta
import time
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict

# Import modules
from support_agent_tools import TOOLS
from support_agent_orchestrator import SupportAgentOrchestrator

OUTPUT_DIR = Path.cwd()
SPEC_PATH = OUTPUT_DIR / "support_agent_spec.yaml"
DB_PATH = OUTPUT_DIR / "data" / "customer_support.db"
os.makedirs(OUTPUT_DIR / "data", exist_ok=True)
os.makedirs(OUTPUT_DIR / "trajectories", exist_ok=True)


# Test scenarios with multi-turn conversations
SCENARIOS = [
    {
        "name": "Scenario 1: Mobile Phone - Within Window, Unopened",
        "order_id": "ORD-001-MOBILE",
        "customer_id": "CUST-001",
        "customer_name": "John Smith",
        "conversation": [
            "Hi, I'd like to return my Samsung Galaxy S24 from order ORD-001-MOBILE. I changed my mind and want a refund.",
            "Yes, it's still unopened in the original box.",
            "Thank you!",
        ],
        "expected_decision": "APPROVE",
        "expected_amount_approx": 700,  # 800 - 20 (shipping) - 80 (tax) = 700
    },
    # {
    #     "name": "Scenario 2: Shoes - Outside 30-Day Window",
    #     "order_id": "ORD-002-SHOES",
    #     "customer_id": "CUST-002",
    #     "customer_name": "Sarah Johnson",
    #     "conversation": [
    #         "Hi! My order is ORD-002-SHOES (Nike Running Shoes). I never wore them and want a refund.",
    #         "I'm requesting the refund now.",
    #     ],
    #     "expected_decision": "REJECT",
    #     "expected_amount_approx": 0,  # Outside 30-day window
    # },
    {
        "name": "Scenario 2: Shoes - Outside 30-Day Window",
        "order_id": "ORD-002-SHOES",
        "customer_id": "CUST-002",
        "customer_name": "Sarah Johnson",
        "conversation": [
            "Hi! My order is ORD-002-SHOES (Nike Running Shoes). I never wore them and want a refund.",
            "I'm requesting the refund now.",
        ],
        "expected_decision": "REJECT",
        "expected_amount_approx": 0,  # Outside 30-day window
    },
    {
        "name": "Scenario 3: T-Shirt - Within Window, Worn",
        "order_id": "ORD-003-SHIRT",
        "customer_id": "CUST-003",
        "customer_name": "Mike Davis",
        "conversation": [
            "I ordered a cotton t-shirt (ORD-003-SHIRT) but it's the wrong size. Can I get a refund?",
            "I tried it on once but it doesn't fit. I want to return it.",
        ],
        "expected_decision": "APPROVE",
        "expected_amount_approx": 19,  # 30 - 8 (shipping) - 3 (tax) = 19
    },
    {
        "name": "Scenario 4: Laptop - Within Window, DEFECTIVE",
        "order_id": "ORD-004-LAPTOP",
        "customer_id": "CUST-004",
        "customer_name": "Emily Chen",
        "conversation": [
            "My laptop order (ORD-004-LAPTOP) arrived with a broken screen. This is unacceptable!",
            "The screen is cracked and doesn't work at all. I want a refund.",
        ],
        "expected_decision": "APPROVE",
        "expected_amount_approx": 1030,  # 1200 - 50 (shipping) - 120 (tax) + 0 (no return shipping deduction for defective)
    },
]


async def run_scenario(scenario: Dict) -> Dict:
    """Run a single multi-turn conversation scenario"""
    
    print(f"\n\n{'#'*100}")
    print(f"# {scenario['name']}")
    print(f"#{'─'*98}#")
    print(f"# Order: {scenario['order_id']:20} | Customer: {scenario['customer_name']:20} | Expected: {scenario['expected_decision']:10}")
    print(f"#{'─'*98}#")
    print(f"{'#'*100}\n")
    
    # Create orchestrator
    orchestrator = SupportAgentOrchestrator(
        spec_path=str(SPEC_PATH),
        tool_registry=TOOLS,
    )
    
    # Set initial context
    orchestrator.customer_id = scenario["customer_id"]
    orchestrator.order_id = scenario["order_id"]
    
    # Run multi-turn conversation
    print(f"Starting conversation with {scenario['customer_name']}...\n")
    
    results = []
    for turn_idx, customer_message in enumerate(scenario["conversation"], 1):
        print(f"\n>>> TURN {turn_idx}")
        result = await orchestrator.process_customer_message(customer_message)
        results.append(result)
        
        # Check if this is final turn (last message gets decision)
        if turn_idx == len(scenario["conversation"]):
            print(f"\n✓ Conversation completed after {turn_idx} turn(s)")
    
    # Print summary
    orchestrator.print_summary()
    
    # Save trajectory
    output_file = OUTPUT_DIR / "trajectories" / f"trajectory_{scenario['order_id']}_{int(time.time())}.json"
    os.makedirs(output_file.parent, exist_ok=True)
    orchestrator.save_trajectory(str(output_file))
    
    # Validate results
    final_result = results[-1]
    actual_decision = final_result.get("decision", "ERROR")
    actual_amount = final_result.get("refund_amount", 0)
    
    decision_match = actual_decision == scenario["expected_decision"]
    amount_match = abs(actual_amount - scenario["expected_amount_approx"]) < 1  # Within $1
    
    print(f"\n{'─'*100}")
    print(f" VALIDATION")
    print(f"{'─'*100}")
    print(f"Expected Decision: {scenario['expected_decision']:15} | Actual: {actual_decision:15} | Match: {'✓' if decision_match else '✗'}")
    print(f"Expected Amount:  ${scenario['expected_amount_approx']:10.2f}  | Actual: ${actual_amount:10.2f} | Match: {'✓' if amount_match else '✗'}")
    
    return {
        "scenario_name": scenario["name"],
        "order_id": scenario["order_id"],
        "customer_id": scenario["customer_id"],
        "turns": len(scenario["conversation"]),
        "decision": actual_decision,
        "decision_match": decision_match,
        "refund_amount": actual_amount,
        "amount_match": amount_match,
        "refund_id": final_result.get("refund_id", ""),
        "idempotency_key": final_result.get("idempotency_key", ""),
        "success": final_result.get("success", False),
    }


async def test_idempotency(scenario: Dict):
    """Test idempotency: same request twice should NOT create duplicate refund"""
    
    print(f"\n\n{'#'*100}")
    print(f"# IDEMPOTENCY TEST: {scenario['name']}")
    print(f"# Testing: Same refund request submitted twice should NOT process double refund")
    print(f"{'#'*100}\n")
    
    orchestrator = SupportAgentOrchestrator(
        spec_path=str(SPEC_PATH),
        tool_registry=TOOLS,
    )
    
    orchestrator.customer_id = scenario["customer_id"]
    orchestrator.order_id = scenario["order_id"]
    
    # First request
    print("Request #1: First refund request")
    result1 = await orchestrator.process_customer_message(scenario["conversation"][0])
    refund_id_1 = result1.get("refund_id", "")
    idempotency_key_1 = result1.get("idempotency_key", "")
    
    print(f"\nRefund ID: {refund_id_1}")
    print(f"Idempotency Key: {idempotency_key_1}")
    
    # Second request (exact same message)
    print("\n" + "─"*100)
    print("Request #2: Duplicate refund request (same message)")
    
    # Create new orchestrator with same customer/order
    orchestrator2 = SupportAgentOrchestrator(
        spec_path=str(SPEC_PATH),
        tool_registry=TOOLS,
    )
    
    orchestrator2.customer_id = scenario["customer_id"]
    orchestrator2.order_id = scenario["order_id"]
    
    result2 = await orchestrator2.process_customer_message(scenario["conversation"][0])
    refund_id_2 = result2.get("refund_id", "")
    idempotency_key_2 = result2.get("idempotency_key", "")
    
    print(f"\nRefund ID: {refund_id_2}")
    print(f"Idempotency Key: {idempotency_key_2}")
    
    # Validation
    print(f"\n{'─'*100}")
    print(f" IDEMPOTENCY VALIDATION")
    print(f"{'─'*100}")
    
    keys_match = idempotency_key_1 == idempotency_key_2
    print(f"Idempotency Keys Match: {'✓' if keys_match else '✗'}")
    
    # Check database: should only have ONE refund record for this order
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM refunds WHERE order_id = ?", (scenario["order_id"],))
    refund_count = cursor.fetchone()[0]
    conn.close()
    
    no_double_refund = refund_count <= 1
    print(f"No Double Refunds in DB: {'✓' if no_double_refund else '✗'} (Count: {refund_count})")
    
    return {
        "scenario_name": scenario["name"],
        "idempotency_key_1": idempotency_key_1,
        "idempotency_key_2": idempotency_key_2,
        "keys_match": keys_match,
        "refund_count_in_db": refund_count,
        "no_double_refund": no_double_refund,
    }


async def main():
    """Main entry point"""
    
    print("\n" + "="*100)
    print(" CUSTOMER SUPPORT REFUND AGENT - MULTI-TURN CONVERSATION TEST SUITE")
    print("="*100)
    
    print("\nLoading components...")
    print(f"✓ Database: {DB_PATH}")
    print(f"✓ Tools: {len(TOOLS)} tools loaded")
    print(f"✓ Spec: {SPEC_PATH}")
    
    # Run all scenarios
    scenario_results = []
    
    for scenario in SCENARIOS:
        try:
            result = await run_scenario(scenario)
            scenario_results.append(result)
        except Exception as e:
            print(f"\n✗ Scenario failed: {e}")
            import traceback
            traceback.print_exc()
    
    # Test idempotency on first scenario
    print(f"\n\n{'='*100}")
    print(" IDEMPOTENCY TESTS")
    print(f"{'='*100}")
    
    idempotency_results = []
    idempotency_results.append(await test_idempotency(SCENARIOS[0]))
    
    # Generate summary report
    print(f"\n\n{'='*100}")
    print(" FINAL SUMMARY")
    print(f"{'='*100}\n")
    
    summary = {
        "test_timestamp": datetime.now().isoformat(),
        "total_scenarios": len(SCENARIOS),
        "passed_scenarios": sum(1 for r in scenario_results if r.get("decision_match") and r.get("amount_match")),
        "scenarios": scenario_results,
        "idempotency_tests": idempotency_results,
    }
    
    print("Scenario Results:")
    print(f"{'Scenario':<50} {'Decision':<10} {'Amount':<10} {'Status':<10}")
    print("─" * 80)
    for result in scenario_results:
        status = "✓ PASS" if (result.get("decision_match") and result.get("amount_match")) else "✗ FAIL"
        print(f"{result['scenario_name']:<50} {result['decision']:<10} ${result['refund_amount']:<9.2f} {status:<10}")
    
    print(f"\nIdempotency:")
    for result in idempotency_results:
        status = "✓ PASS" if result.get("no_double_refund") else "✗ FAIL"
        print(f"  {result['scenario_name']}: {status}")
    
    print(f"\nOverall: {summary['passed_scenarios']}/{len(SCENARIOS)} scenarios passed")
    
    # Save summary
    summary_file = OUTPUT_DIR / "test_summary.json"
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)
    
    print(f"\n✓ Summary saved to {summary_file}")
    print(f"\n{'='*100}\n")


if __name__ == "__main__":
    asyncio.run(main())
