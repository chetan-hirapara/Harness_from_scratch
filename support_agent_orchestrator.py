"""
Customer Support Refund Agent - Multi-Turn Orchestrator

Handles:
- Multi-turn conversations (customer sends messages, agent responds)
- State management (conversation history, context)
- Tool pipeline execution
- Idempotency (prevent double refunds)
- Full trajectory capture
"""

import asyncio
import json
import sqlite3
import yaml
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from datetime import datetime
from collections import defaultdict, deque

import llm_client


@dataclass
class ConversationMessage:
    """Single message in conversation"""
    role: str  # "customer" or "agent"
    text: str
    timestamp: str
    intent: Optional[str] = None
    order_id: Optional[str] = None


@dataclass
class TrajectoryStep:
    """Single tool execution"""
    step_id: int
    tool_name: str
    timestamp: str
    latency_ms: float
    success: bool
    inputs: Dict[str, Any] = field(default_factory=dict)
    outputs: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    depends_on: List[str] = field(default_factory=list)


@dataclass
class ExecutionTrajectory:
    """Complete conversation + execution trace"""
    conversation_id: str
    customer_id: str
    start_timestamp: str
    end_timestamp: str
    steps: List[TrajectoryStep] = field(default_factory=list)
    messages: List[ConversationMessage] = field(default_factory=list)
    
    total_latency_ms: float = 0.0
    success: bool = False
    final_decision: str = "PENDING"
    final_refund_amount: float = 0.0
    refund_id: str = ""
    idempotency_key: str = ""
    
    def to_dict(self):
        steps_list = []
        for step in self.steps:
            steps_list.append({
                "step_id": step.step_id,
                "tool_name": step.tool_name,
                "timestamp": step.timestamp,
                "latency_ms": step.latency_ms,
                "success": step.success,
                "inputs": {k: str(v)[:100] for k, v in step.inputs.items()},
                "outputs": {k: str(v)[:100] for k, v in step.outputs.items()},
                "error": step.error,
                "depends_on": step.depends_on,
            })
        
        messages_list = []
        for msg in self.messages:
            messages_list.append({
                "role": msg.role,
                "text": msg.text,
                "timestamp": msg.timestamp,
                "intent": msg.intent,
                "order_id": msg.order_id,
            })
        
        return {
            "conversation_id": self.conversation_id,
            "customer_id": self.customer_id,
            "start_timestamp": self.start_timestamp,
            "end_timestamp": self.end_timestamp,
            "total_latency_ms": self.total_latency_ms,
            "success": self.success,
            "final_decision": self.final_decision,
            "final_refund_amount": self.final_refund_amount,
            "refund_id": self.refund_id,
            "idempotency_key": self.idempotency_key,
            "steps": steps_list,
            "messages": messages_list,
        }


class SupportAgentOrchestrator:
    """
    Multi-turn conversation orchestrator for customer support refund agent
    
    Features:
    - Maintains conversation state
    - Routes through 15-tool pipeline
    - Prevents double refunds via idempotency
    - Full trajectory capture
    """
    
    def __init__(self, spec_path: str, tool_registry: Dict):
        """Initialize orchestrator"""
        self.spec = self._load_spec(spec_path)
        self.tools = tool_registry
        self.tool_defs = self.spec.get("tools", {})
        
        # Configure the shared LLM client from the spec's llm section
        llm_client.configure(self.spec.get("llm", {}))
        
        # DAG structures
        self.dag = {}
        self.reverse_dag = {}
        self.execution_levels = {}
        
        # Conversation state
        self.conversation_id = str(uuid.uuid4())[:8]
        self.customer_id = ""
        self.order_id = ""
        self.messages: List[ConversationMessage] = []
        self.context: Dict[str, Any] = {}
        
        # Trajectory
        self.trajectory = None
        self.step_counter = 0
        
        # Build DAG
        self._build_dag()
        self._compute_execution_levels()
    
    def _load_spec(self, spec_path: str) -> Dict:
        """Load YAML spec"""
        with open(spec_path, 'r') as f:
            return yaml.safe_load(f)
    
    def _build_dag(self):
        """Build dependency graph"""
        for tool_name, tool_def in self.tool_defs.items():
            deps = tool_def.get("depends_on", [])
            self.dag[tool_name] = deps
            
            if tool_name not in self.reverse_dag:
                self.reverse_dag[tool_name] = []
            
            for dep in deps:
                if dep not in self.reverse_dag:
                    self.reverse_dag[dep] = []
                self.reverse_dag[dep].append(tool_name)
    
    def _compute_execution_levels(self):
        """Compute execution levels"""
        in_degree = {tool: len(self.dag.get(tool, [])) for tool in self.dag}
        queue = deque([tool for tool in in_degree if in_degree[tool] == 0])
        level = 0
        
        while queue:
            next_queue = deque()
            
            while queue:
                tool = queue.popleft()
                self.execution_levels[tool] = level
                
                for dependent in self.reverse_dag.get(tool, []):
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0:
                        next_queue.append(dependent)
            
            queue = next_queue
            if queue:
                level += 1
    
    async def process_customer_message(self, customer_message: str) -> Dict[str, Any]:
        """
        Process single customer message through the tool pipeline
        
        Returns: Agent response + refund details
        """
        # Initialize trajectory
        if not self.trajectory:
            self.trajectory = ExecutionTrajectory(
                conversation_id=self.conversation_id,
                customer_id=self.customer_id,
                start_timestamp=datetime.now().isoformat(),
                end_timestamp="",
            )
        
        total_start = asyncio.get_event_loop().time()
        
        # Add customer message to conversation
        self.messages.append(ConversationMessage(
            role="customer",
            text=customer_message,
            timestamp=datetime.now().isoformat()
        ))
        self.trajectory.messages.append(self.messages[-1])
        
        print(f"\n{'='*100}")
        print(f" CUSTOMER: {customer_message}")
        print(f"{'='*100}")
        
        # Execute tool pipeline
        tool_outputs = {}
        
        # Group tools by level
        levels_dict = defaultdict(list)
        for tool, level in self.execution_levels.items():
            levels_dict[level].append(tool)
        
        try:
            for level in sorted(levels_dict.keys()):
                tools_at_level = levels_dict[level]
                print(f"\n--- Level {level}: {tools_at_level} ---")
                
                # Create tasks for all tools at this level
                tasks = {}
                for tool_name in tools_at_level:
                    tasks[tool_name] = asyncio.create_task(
                        self._execute_tool_with_retry(
                            tool_name=tool_name,
                            tool_outputs=tool_outputs,
                            message=customer_message,
                            depends_on=self.tool_defs[tool_name].get("depends_on", [])
                        )
                    )
                
                # Wait for all tasks
                results = await asyncio.gather(*tasks.values(), return_exceptions=True)
                
                # Process results
                for tool_name, result in zip(tasks.keys(), results):
                    if isinstance(result, Exception):
                        tool_outputs[tool_name] = None
                        print(f"  ✗ {tool_name}: {result}")
                    else:
                        tool_outputs[tool_name] = result
                        print(f"  ✓ {tool_name}")
            
            # Extract key info from outputs
            self.context = tool_outputs
            
            # Get final decision and response
            agent_response = tool_outputs.get("generate_customer_response", {}).get("response", "")
            refund_decision = tool_outputs.get("make_refund_decision", {}).get("decision", "PENDING")
            refund_amount = tool_outputs.get("make_refund_decision", {}).get("refund_amount", 0)
            refund_id = tool_outputs.get("make_refund_decision", {}).get("refund_id", "")
            idempotency_key = tool_outputs.get("check_idempotency", {}).get("idempotency_key", "")
            
            # Add agent response to conversation
            self.messages.append(ConversationMessage(
                role="agent",
                text=agent_response,
                timestamp=datetime.now().isoformat()
            ))
            self.trajectory.messages.append(self.messages[-1])
            
            # Update trajectory
            self.trajectory.success = True
            self.trajectory.final_decision = refund_decision
            self.trajectory.final_refund_amount = refund_amount
            self.trajectory.refund_id = refund_id
            self.trajectory.idempotency_key = idempotency_key
            
            print(f"\n{'─'*100}")
            print(f" AGENT: {agent_response[:200]}...")
            print(f"{'─'*100}")
            print(f"\nDECISION: {refund_decision} | AMOUNT: ${refund_amount:.2f} | REFUND_ID: {refund_id}")
            
            return {
                "success": True,
                "agent_response": agent_response,
                "decision": refund_decision,
                "refund_amount": refund_amount,
                "refund_id": refund_id,
                "idempotency_key": idempotency_key,
            }
        
        except Exception as e:
            self.trajectory.success = False
            print(f"\n✗ Pipeline failed: {e}")
            return {
                "success": False,
                "error": str(e),
            }
        
        finally:
            # Finalize trajectory
            self.trajectory.end_timestamp = datetime.now().isoformat()
            self.trajectory.total_latency_ms = (asyncio.get_event_loop().time() - total_start) * 1000
    
    async def _execute_tool_with_retry(
        self,
        tool_name: str,
        tool_outputs: Dict[str, Any],
        message: str,
        depends_on: List[str],
        attempt: int = 0
    ) -> Any:
        """Execute tool with retry logic"""
        step_start = asyncio.get_event_loop().time()
        
        tool_def = self.tool_defs.get(tool_name)
        max_retries = tool_def.get("retries", 1)
        
        # Prepare inputs from dependencies
        tool_inputs = {
            "message": message,
            "conversation_id": self.conversation_id,
            "customer_id": self.customer_id,
            "order_id": self.order_id,
        }
        
        # Pass dependencies as named parameters (not unpacked)
        for dep in depends_on:
            if dep in tool_outputs and tool_outputs[dep]:
                tool_inputs[dep] = tool_outputs[dep]
        
        # Execute
        try:
            if tool_name not in self.tools:
                raise Exception(f"Tool {tool_name} not in registry")
            
            tool_func = self.tools[tool_name]
            outputs = await tool_func(**tool_inputs)
            
            # Ensure outputs is a dict
            if not isinstance(outputs, dict):
                outputs = {"result": outputs}
            
            # Record in trajectory
            latency_ms = (asyncio.get_event_loop().time() - step_start) * 1000
            step = TrajectoryStep(
                step_id=self.step_counter,
                tool_name=tool_name,
                timestamp=datetime.now().isoformat(),
                latency_ms=latency_ms,
                success=True,
                inputs=tool_inputs,
                outputs=outputs,
                depends_on=depends_on,
            )
            self.step_counter += 1
            self.trajectory.steps.append(step)
            
            # Update context
            self.customer_id = tool_inputs.get("customer_id", self.customer_id)
            self.order_id = tool_inputs.get("order_id", self.order_id)
            
            return outputs
        
        except Exception as e:
            # Retry logic
            if attempt < max_retries:
                await asyncio.sleep(0.1 * (attempt + 1))
                return await self._execute_tool_with_retry(
                    tool_name, tool_outputs, message, depends_on, attempt + 1
                )
            
            raise Exception(f"Tool {tool_name} failed after {max_retries} retries: {e}")
    
    def save_trajectory(self, output_path: str):
        """Save trajectory as JSON"""
        if self.trajectory:
            with open(output_path, 'w') as f:
                json.dump(self.trajectory.to_dict(), f, indent=2)
            print(f"\n✓ Trajectory saved to {output_path}")
    
    def print_summary(self):
        """Print conversation summary"""
        if not self.trajectory:
            return
        
        print(f"\n{'='*100}")
        print(" CONVERSATION SUMMARY")
        print(f"{'='*100}")
        print(f"Conversation ID: {self.trajectory.conversation_id}")
        print(f"Customer ID: {self.customer_id}")
        print(f"Order ID: {self.order_id}")
        print(f"Total Latency: {self.trajectory.total_latency_ms:.1f}ms")
        print(f"Status: {'✓ SUCCESS' if self.trajectory.success else '✗ FAILED'}")
        print(f"\nFinal Decision: {self.trajectory.final_decision}")
        print(f"Refund Amount: ${self.trajectory.final_refund_amount:.2f}")
        print(f"Refund ID: {self.trajectory.refund_id}")
        print(f"Idempotency Key: {self.trajectory.idempotency_key}")
        print(f"\nMessages: {len(self.trajectory.messages)}")
        print(f"Tools Executed: {len(self.trajectory.steps)}")
