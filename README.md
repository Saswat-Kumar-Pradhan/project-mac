# MACADS (Multi-Agent Code Analysis & Documentation System)

MACADS is an advanced AI-powered platform designed to perform comprehensive code analysis, generate multi-persona documentation, and provide intelligent search capabilities for complex codebases. By leveraging multiple specialized agents, MACADS transforms raw code into actionable insights for both developers and product managers.

---

## 🚀 Features

- **Multi-Agent Analysis:** Specialized agents analyze code for technical details (SDE persona) and business logic (PM persona).
- **Automated Documentation:** Generate high-quality documentation, including overview, installation guides, and API details.
- **Architecture Visualization:** Automatically generates Mermaid-based architecture diagrams.
- **Intelligent Q&A Chat:** Chat with your codebase using RAG (Retrieval-Augmented Generation) powered by ChromaDB.
- **GitHub Integration:** Clone and analyze repositories directly from GitHub URLs.
- **PDF Export:** Export generated documentation into professional PDF reports.
- **Admin Dashboard:** Monitor system metrics and manage users.

---

## 🛠️ Tech Stack

- **Backend:** FastAPI, SQLAlchemy (SQLite), OpenAI (GPT-4o), LangChain, ChromaDB.
- **Frontend:** Streamlit.
- **Documentation:** Markdown, Mermaid.js.

---

## 💻 Installation & Setup (Windows)

Follow these steps to set up MACADS on your Windows machine.

### 1. Clone the Repository

```bash
git clone https://github.com/your-username/MACADS.git
cd MACADS
```

### 2. Set Up Virtual Environment

It is recommended to use a virtual environment to manage dependencies.

```powershell
# Create virtual environment
python -m venv venv

# Activate virtual environment
.\venv\Scripts\activate
```

### 3. Environment Configuration

Create a `.env` file in the root directory and add your keys. You can use the template below:

```env
SECRET_KEY=your_super_secret_key
OPENAI_API_KEY=your_openai_api_key_here

# Langfuse Configuration (Optional)
LANGFUSE_SECRET_KEY=your_langfuse_secret_key
LANGFUSE_PUBLIC_KEY=your_langfuse_public_key
LANGFUSE_HOST=https://us.cloud.langfuse.com

# API Configuration
API_URL=http://localhost:8000
```

### 4. Backend Setup

```command prompt
# Navigate to backend folder
cd backend

# Install requirements
pip install -r requirements.txt

# Run the backend server
uvicorn main:app --reload
```
The backend will be available at `http://localhost:8000`.

### 5. Frontend Setup

Open a **new terminal** (and remember to activate the `venv` as shown in Step 2).

```command prompt
# Navigate to frontend folder
cd frontend

# Install requirements
pip install -r requirements.txt

# Run the Streamlit app
streamlit run app.py
```
The frontend will be available at `http://localhost:8501`.

---

## 📖 Usage

1. **Register/Login:** Create an account to start managing your projects.
2. **Upload Project:** Upload a `.zip` file of your codebase or provide a GitHub URL.
3. **Analyze:** Let the agents scan and analyze the repository.
4. **Generate Docs:** Trigger documentation generation for SDE and PM personas.
5. **Chat:** Use the AI assistant to ask specific questions about the code.
6. **Export:** Download the final documentation as a PDF.

---

## 🛡️ License

This project is licensed under the MIT License - see the LICENSE file for details.
