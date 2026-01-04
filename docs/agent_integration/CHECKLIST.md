# Integration Checklist

## Pre-Integration

- [ ] Backup current database
- [ ] Review existing pipeline configurations
- [ ] Verify Python version (3.10+)
- [ ] Check Django version (4.0+)

## Installation

### Step 1: Configuration
- [ ] Add `'agent_integration'` to `INSTALLED_APPS` in `pipeline/settings.py`
- [ ] Add `path('agent/', include('agent_integration.urls'))` to `pipeline/urls.py`

### Step 2: Database
- [ ] Run `python manage.py makemigrations agent_integration`
- [ ] Review migration file
- [ ] Run `python manage.py migrate agent_integration`
- [ ] Verify tables created: `agent_integration_agentrun`, etc.

### Step 3: Verification
- [ ] Run `python manage.py check`
- [ ] Run `python manage.py test agent_integration`
- [ ] Start server: `python manage.py runserver`
- [ ] Access admin: http://localhost:8000/admin/

## Testing

### Unit Tests
- [ ] Run: `python manage.py test agent_integration.tests.RuntimeSpecBuilderTest`
- [ ] Run: `python manage.py test agent_integration.tests.GuardrailEngineTest`
- [ ] Run: `python manage.py test agent_integration.tests.ToolRegistryTest`
- [ ] Run: `python manage.py test agent_integration.tests.AgentExecutionTest`

### Integration Tests
- [ ] Create test pipeline with 2-3 nodes
- [ ] Execute via agent: `start_agent_execution(execution)`
- [ ] Verify AgentRun created
- [ ] Verify AgentDecisions recorded
- [ ] Verify ToolExecutions created
- [ ] Check execution completed successfully

### API Tests
- [ ] Test POST /agent/pipelines/<id>/execute/
- [ ] Test GET /agent/runs/<id>/
- [ ] Test GET /agent/runs/<id>/decisions/
- [ ] Test GET /agent/runs/<id>/spec/

## Admin Interface

- [ ] Navigate to Django admin
- [ ] Check "Agent Integration" section visible
- [ ] Browse AgentRun records
- [ ] Browse AgentDecision records
- [ ] Browse ToolExecution records
- [ ] Browse RuntimeSpec records

## Functional Testing

### Basic Execution
- [ ] Create simple linear pipeline (Node A → Node B)
- [ ] Trigger agent execution
- [ ] Verify both nodes execute in order
- [ ] Check outputs produced correctly

### Guardrail Testing
- [ ] Verify dependencies enforced (Node B requires Node A)
- [ ] Verify duplicate execution blocked
- [ ] Verify max iterations enforced
- [ ] Verify deadlock detection works

### Human Intervention
- [ ] Create pipeline that requires intervention (TODO: implement trigger)
- [ ] Verify status changes to `waiting_for_human`
- [ ] Respond via API
- [ ] Verify execution resumes

### Error Handling
- [ ] Create node with invalid code
- [ ] Trigger agent execution
- [ ] Verify error captured in AgentDecision
- [ ] Verify execution marked as failed
- [ ] Verify no data corruption

## Performance Testing

- [ ] Execute pipeline with 5 nodes
- [ ] Execute pipeline with 10 nodes
- [ ] Check execution time reasonable
- [ ] Monitor memory usage
- [ ] Check database query count

## Security Review

- [ ] Verify authentication required for API endpoints
- [ ] Check authorization (users can only see their runs)
- [ ] Verify no raw artifact data in API responses
- [ ] Check guardrails cannot be bypassed
- [ ] Verify runtime specs are immutable

## Documentation Review

- [ ] Read README.md
- [ ] Read INTEGRATION.md
- [ ] Read IMPLEMENTATION_SUMMARY.md
- [ ] Verify all examples work
- [ ] Check API docs match implementation

## Production Readiness

### Required Before Production
- [ ] Implement actual LLM integration (replace placeholder)
- [ ] Add Celery for async execution
- [ ] Configure rate limiting
- [ ] Set up monitoring (Sentry, DataDog, etc.)
- [ ] Enable HTTPS
- [ ] Configure proper SECRET_KEY
- [ ] Set DEBUG=False
- [ ] Configure allowed hosts
- [ ] Set up database backups
- [ ] Configure log aggregation

### Recommended Before Production
- [ ] Add WebSocket support for streaming
- [ ] Implement cost tracking (LLM API costs)
- [ ] Add performance metrics
- [ ] Create monitoring dashboard
- [ ] Set up alerting
- [ ] Document incident response
- [ ] Create runbook for common issues

## Rollback Plan

If issues occur:

1. **Immediate Rollback**
   ```bash
   # Revert migrations
   python manage.py migrate agent_integration zero
   
   # Remove from settings
   # Comment out 'agent_integration' in INSTALLED_APPS
   
   # Remove URLs
   # Comment out agent URLs in urls.py
   
   # Restart server
   python manage.py runserver
   ```

2. **Data Preservation**
   - Agent data is in separate tables
   - Core pipeline data unaffected
   - Can export agent data before rollback:
     ```bash
     python manage.py dumpdata agent_integration > agent_backup.json
     ```

3. **Restore Later**
   - Re-enable in settings
   - Run migrations again
   - Load backed up data:
     ```bash
     python manage.py loaddata agent_backup.json
     ```

## Post-Integration

- [ ] Monitor logs for errors
- [ ] Check agent execution success rate
- [ ] Review decision quality
- [ ] Gather user feedback
- [ ] Document any issues encountered
- [ ] Plan next iteration

## Sign-Off

- [ ] Developer: _______________  Date: _______
- [ ] QA: _______________  Date: _______
- [ ] DevOps: _______________  Date: _______
- [ ] Product Owner: _______________  Date: _______

## Notes

Use this space to record any issues, observations, or deviations from the plan:

```
[Empty - add notes as needed]
```

## Success Criteria

✅ Installation complete when:
- All tests pass
- Agent can execute sample pipeline
- Admin interface accessible
- API endpoints respond correctly
- No errors in logs

✅ Production ready when:
- LLM integration implemented
- Async execution working
- Monitoring configured
- Security review passed
- Performance acceptable
- Documentation complete
