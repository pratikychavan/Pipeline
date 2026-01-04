# Pipeline Orchestration System

**An AI-powered pipeline orchestration platform with LLM-driven execution.**

## Quick Start

```bash
# 1. Set up environment
export OPENAI_API_KEY="sk-..."

# 2. Install dependencies
pip install django openai matplotlib numpy pandas

# 3. Run migrations
python manage.py migrate

# 4. Start server
python manage.py runserver

# 5. Open browser
http://localhost:8000
```

## Documentation

📚 **[Complete System Documentation](SYSTEM_DOCUMENTATION.md)** - Everything you need to know

### Quick Links

- **User Guide**: See SYSTEM_DOCUMENTATION.md → Section 6
- **API Reference**: See SYSTEM_DOCUMENTATION.md → Section 7
- **Development**: See SYSTEM_DOCUMENTATION.md → Section 8
- **Architecture**: See docs/agent_integration/ for detailed component docs

## Features

✅ Visual pipeline builder with drag-and-drop nodes  
✅ AI-powered execution with OpenAI GPT-4o-mini  
✅ Real-time monitoring and decision tracking  
✅ Safety guardrails (loop detection, deadlock prevention)  
✅ Human-in-the-loop approval flows  
✅ Artifact-based data flow between nodes  

## Project Structure

```
pipeline/
├── SYSTEM_DOCUMENTATION.md    # 📚 Complete documentation
├── README.md                   # 👈 You are here
├── demo_agentic_run.py        # 🚀 Demo script
├── manage.py                   # Django management
│
├── core/                       # Pipeline management app
├── agent_integration/          # Agent orchestration app
├── examples/                   # Example scripts
└── docs/                       # Additional documentation
```

## Example: Starting an Agent Run

### Via UI
1. Go to http://localhost:8000/agent/dashboard/
2. Click "Start New Agent Run"
3. Select your pipeline
4. Add context data (customer_id, etc.)
5. Click "Start"

### Via Python
```python
python demo_agentic_run.py
```

### Via API
```bash
curl -X POST http://localhost:8000/agent/pipelines/<uuid>/start/ \
  -H "Content-Type: application/json" \
  -d '{
    "context_data": {"customer_id": 12345},
    "max_steps": 100,
    "temperature": 0.3
  }'
```

## Architecture

```
UI Layer → Agent Layer → Pipeline Layer → Data Layer
           (LLM)         (Nodes)           (SQLite)
```

**Key Components:**
- **LLM Planner**: Makes intelligent decisions using OpenAI
- **Guardrails**: Ensures safe execution
- **Node Executor**: Runs Python code in isolated environments
- **WarpDrive I/O**: Artifact-based data flow

## Status

✅ **Production Ready** - OpenAI integration complete  
✅ **UI Complete** - Dashboard, graph view, monitoring  
✅ **Tested** - Successful multi-node executions  

## License

MIT License - See LICENSE file for details

## Support

- 📖 Full Documentation: [SYSTEM_DOCUMENTATION.md](SYSTEM_DOCUMENTATION.md)
- 🐛 Issues: Create a GitHub issue
- 💬 Questions: Check documentation first

---

**Built with Django 6.0 + OpenAI GPT-4o-mini**
