# MACADS – Multi-Agent Code Analysis & Documentation System

## Setup (one time)

```bash
# 1. Create a virtual environment
python3 -m venv venv

# 2. Activate it
source venv/bin/activate

# 3. Install all dependencies
pip install -r backend/requirements.txt
pip install -r frontend/requirements.txt
```

## Configure

Edit `.env` and add your OpenAI API key:

```
OPENAI_API_KEY=sk-...your-key-here...
```

## Run

Open **two terminal tabs**, both with the venv activated (`source venv/bin/activate`).

**Terminal 1 — Backend:**
```bash
source venv/bin/activate
cd backend
uvicorn main:app --reload --port 8000
```

**Terminal 2 — Frontend:**
```bash
source venv/bin/activate
cd frontend
streamlit run app.py --server.port 8501
```

- Backend API docs: http://localhost:8000/docs  
- Frontend UI:      http://localhost:8501

## Stop

Press `Ctrl+C` in each terminal.
