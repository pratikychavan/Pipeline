"""
INVALID EXAMPLE - Security Violations

This example demonstrates code that will be REJECTED by the workspace loader.
DO NOT use patterns like these in your agent code.
"""

# VIOLATION: Forbidden import
import os  # ❌ REJECTED - os access not allowed

# VIOLATION: Forbidden import
import subprocess  # ❌ REJECTED - subprocess not allowed

from warpdrive_agent_sdk import Planner, PlannerInput, PlannerDecision, PlannerDecisionType


class MaliciousPlanner(Planner):
    """This planner will be REJECTED due to security violations."""
    
    async def plan_next_action(self, planner_input: PlannerInput) -> PlannerDecision:
        # VIOLATION: Attempting to access filesystem
        os.listdir('/')  # ❌ REJECTED
        
        # VIOLATION: Attempting to execute commands
        subprocess.run(['ls', '-la'])  # ❌ REJECTED
        
        # VIOLATION: Attempting to use eval
        eval("print('malicious')")  # ❌ REJECTED
        
        return PlannerDecision(
            decision_type=PlannerDecisionType.COMPLETE,
            reasoning="This will never execute"
        )
