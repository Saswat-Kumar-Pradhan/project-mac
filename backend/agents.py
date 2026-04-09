import os
from langchain_community.tools import DuckDuckGoSearchRun
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.prompts import PromptTemplate
from langfuse.callback import CallbackHandler
import chromadb
from database import SessionLocal, Project
from sqlalchemy.orm import Session

def get_callbacks():
    if os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"):
        return [CallbackHandler(
            public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
            secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
            host=os.getenv("LANGFUSE_HOST")
        )]
    return []

CHROMA_PATH = os.path.join(os.path.dirname(__file__), "chroma_db")
chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)

def fetch_context_from_chroma(project_id: int, query: str, k: int = 15) -> str:
    try:
        embeddings = OpenAIEmbeddings(api_key=os.getenv("OPENAI_API_KEY"))
        collection = chroma_client.get_collection(name=f"project_{project_id}")
        query_embedding = embeddings.embed_query(query)
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=k
        )
        if not results['documents']:
            return "No context found."
            
        docs = []
        for i, doc in enumerate(results['documents'][0]):
            source = results['metadatas'][0][i].get('source', 'Unknown')
            docs.append(f"--- File: {source} ---\n{doc}\n")
        return "\n".join(docs)
    except Exception as e:
        print(f"ChromaDB lookup failed: {e}")
        return ""

def run_sde_agent(project_id: int, project: Project, llm) -> str:
    context = fetch_context_from_chroma(project_id, "backend architecture schemas database API routes main configuration setup class def function route init", k=15)
    
    try:
        search = DuckDuckGoSearchRun()
        search_query = f"latest official documentation layout architecture patterns for {', '.join(project.frameworks or ['Python'])}"
        web_context = search.run(search_query)
    except Exception:
        web_context = "No live web context found."
        
    prompt = PromptTemplate.from_template(
        "You are an expert Software Engineer writing deep technical documentation for other engineers.\n"
        "Analyze the following code context and write a comprehensive technical markdown document.\n"
        "Critically obey the following user-provided context injected during the analysis phase: {analysis_context}\n"
        "Include sections for Setup, Architecture, Core Dependencies, and API Routes if they exist.\n"
        "Use the provided Web Context to include up-to-date best practices or official documentation links natively.\n\n"
        "Repository Frameworks: {frameworks}\n"
        "Entry Points: {entry_points}\n\n"
        "Web Context (Latest Online Trends):\n{web_context}\n\n"
        "Code Context:\n{context}\n\n"
        "Technical Documentation:"
    )
    chain = prompt | llm
    res = chain.invoke({
        "frameworks": ", ".join(project.frameworks or []),
        "entry_points": ", ".join(project.entry_points or []),
        "web_context": web_context,
        "context": context,
        "analysis_context": project.analysis_context or "Not provided by user."
    }, config={"callbacks": get_callbacks()})
    return res.content

def run_pm_agent(project_id: int, project: Project, llm) -> str:
    context = fetch_context_from_chroma(project_id, "features use cases user roles business logic purpose main overview requirements auth dashboard", k=12)
    prompt = PromptTemplate.from_template(
        "You are an expert Product Manager writing product documentation for stakeholders.\n"
        "Analyze the following code context and write a high-level product summary in Markdown.\n"
        "Critically obey the following user-provided context injected during the analysis phase: {analysis_context}\n"
        "Include sections for Product Overview, Key Features, Target Personas, and Business Value.\n\n"
        "Repository Built With: {frameworks}\n\n"
        "Code Context:\n{context}\n\n"
        "Product Documentation:"
    )
    chain = prompt | llm
    res = chain.invoke({
        "frameworks": ", ".join(project.frameworks or []),
        "context": context,
        "analysis_context": project.analysis_context or "None provided by user."
    }, config={"callbacks": get_callbacks()})
    return res.content

def run_visual_agent(project_id: int, project: Project, llm) -> str:
    context = fetch_context_from_chroma(project_id, "architecture flow control entry points models relationships database backend frontend", k=10)
    prompt = PromptTemplate.from_template(
        "You are a System Architect creating flowchart diagrams using Mermaid.js format.\n"
        "Based on the following code structure, generate a Mermaid.js diagram that maps out the primary technical flow, architecture, or database schema.\n"
        "Return ONLY the valid raw Mermaid code block (starting with ```mermaid and ending with ```). Do NOT include any other text.\n\n"
        "Frameworks: {frameworks}\n"
        "Entry Points: {entry_points}\n\n"
        "Code Context:\n{context}\n\n"
        "Mermaid Diagram:"
    )
    chain = prompt | llm
    res = chain.invoke({
        "frameworks": ", ".join(project.frameworks or []),
        "entry_points": ", ".join(project.entry_points or []),
        "context": context
    }, config={"callbacks": get_callbacks()})
    return res.content

def generate_documentation_background(project_id: int):
    db: Session = SessionLocal()
    project = db.query(Project).filter(Project.id == project_id).first()
    
    if not project:
        db.close()
        return
        
    try:
        project.status = "generating"
        db.commit()
        
        db.refresh(project)
        if project.status == "paused":
            return
            
        llm = ChatOpenAI(model="gpt-4o-mini", api_key=os.getenv("OPENAI_API_KEY"), temperature=0.2)
        
        personas = [p.upper() for p in project.personas]
        
        if "SDE" in personas:
            project.sde_docs = run_sde_agent(project.id, project, llm)
            
        if "PM" in personas:
            project.pm_docs = run_pm_agent(project.id, project, llm)
            
        project.architecture_diagram = run_visual_agent(project.id, project, llm)
        
        project.status = "documented"
        db.commit()
    except Exception as e:
        print(f"Agent Orchestration Failed: {e}")
        project.status = "failed"
        db.commit()
    finally:
        db.close()
