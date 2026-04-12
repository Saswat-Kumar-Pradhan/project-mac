import os

from langchain_community.tools import DuckDuckGoSearchRun
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.prompts import PromptTemplate
from langfuse.callback import CallbackHandler
from chroma import get_chroma_client
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

def fetch_context_from_chroma(project_id: int, query: str, k: int = 15) -> str:
    collection_name = f"project_{project_id}"
    try:
        collection = get_chroma_client().get_collection(name=collection_name)
    except Exception as e:
        print(f"ChromaDB collection not found for project {project_id}: {e}")
        return ""

    # Try semantic search with OpenAI embeddings first
    try:
        embeddings = OpenAIEmbeddings(api_key=os.getenv("OPENAI_API_KEY"))
        query_embedding = embeddings.embed_query(query)
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=k
        )
        if results['documents']:
            docs = []
            for i, doc in enumerate(results['documents'][0]):
                source = results['metadatas'][0][i].get('source', 'Unknown')
                docs.append(f"--- File: {source} ---\n{doc}\n")
            return "\n".join(docs)
    except Exception as e:
        print(f"Embedding lookup failed (falling back to raw context): {e}")

    # Fallback: return first k stored documents without embedding
    try:
        results = get_chroma_client().get_collection(name=collection_name).get(limit=k, include=["documents", "metadatas"])
        if not results['documents']:
            return "No context found."
        docs = []
        for i, doc in enumerate(results['documents']):
            source = results['metadatas'][i].get('source', 'Unknown') if results['metadatas'] else 'Unknown'
            docs.append(f"--- File: {source} ---\n{doc}\n")
        return "\n".join(docs)
    except Exception as e:
        print(f"ChromaDB fallback also failed: {e}")
        return ""


def run_sde_agent(project_id: int, project: Project, llm) -> str:
    context = fetch_context_from_chroma(
        project_id,
        "backend architecture schemas database API routes main configuration setup class def function route init",
        k=15
    )

    try:
        search = DuckDuckGoSearchRun()
        search_query = f"latest official documentation layout architecture patterns for {', '.join(project.frameworks or ['Python'])}"
        web_context = search.run(search_query)
    except Exception:
        web_context = "No live web context found."

    file_tree = project.file_tree or "Not available."

    prompt = PromptTemplate.from_template(
        "You are an expert Software Engineer writing deep technical documentation for other engineers.\n"
        "Use the EXACT directory structure and file tree provided below — do NOT invent or guess any paths or modules.\n"
        "Critically obey the following user-provided context: {analysis_context}\n\n"
        "Repository Type: {repository_type}\n"
        "Frameworks: {frameworks}\n"
        "Entry Points: {entry_points}\n\n"
        "=== ACTUAL DIRECTORY STRUCTURE ===\n"
        "{file_tree}\n\n"
        "=== CODE CONTEXT (key file excerpts) ===\n"
        "{context}\n\n"
        "=== WEB CONTEXT (latest best practices) ===\n"
        "{web_context}\n\n"
        "Write a comprehensive technical markdown document with these sections:\n"
        "1. Project Overview\n"
        "2. Directory Structure (use the exact tree above)\n"
        "3. Setup & Installation\n"
        "4. Architecture & Data Flow\n"
        "5. Core Modules & Responsibilities\n"
        "6. API Routes (if applicable)\n"
        "7. Key Dependencies\n\n"
        "Technical Documentation:"
    )
    chain = prompt | llm
    res = chain.invoke({
        "repository_type": project.repository_type or "Unknown",
        "frameworks": ", ".join(project.frameworks or []),
        "entry_points": ", ".join(project.entry_points or []),
        "file_tree": file_tree,
        "web_context": web_context,
        "context": context,
        "analysis_context": project.analysis_context or "Not provided by user."
    }, config={"callbacks": get_callbacks()})
    return res.content


def run_pm_agent(project_id: int, project: Project, llm) -> str:
    context = fetch_context_from_chroma(
        project_id,
        "features use cases user roles business logic purpose main overview requirements auth dashboard",
        k=12
    )
    file_tree = project.file_tree or "Not available."

    prompt = PromptTemplate.from_template(
        "You are an expert Product Manager writing product documentation for stakeholders.\n"
        "Base your analysis ONLY on the actual code context and directory structure provided below.\n"
        "Critically obey the following user-provided context: {analysis_context}\n\n"
        "Repository Type: {repository_type}\n"
        "Built With: {frameworks}\n\n"
        "=== ACTUAL DIRECTORY STRUCTURE ===\n"
        "{file_tree}\n\n"
        "=== CODE CONTEXT ===\n"
        "{context}\n\n"
        "Write a high-level product summary in Markdown with these sections:\n"
        "1. Product Overview\n"
        "2. Key Features (derived from actual code, not assumed)\n"
        "3. Target Personas & User Roles\n"
        "4. Tech Stack Summary\n"
        "5. Business Value\n\n"
        "Product Documentation:"
    )
    chain = prompt | llm
    res = chain.invoke({
        "repository_type": project.repository_type or "Unknown",
        "frameworks": ", ".join(project.frameworks or []),
        "file_tree": file_tree,
        "context": context,
        "analysis_context": project.analysis_context or "None provided by user."
    }, config={"callbacks": get_callbacks()})
    return res.content


def run_visual_agent(project_id: int, project: Project, llm) -> str:
    context = fetch_context_from_chroma(
        project_id,
        "architecture flow control entry points models relationships database backend frontend",
        k=10
    )
    file_tree = project.file_tree or "Not available."

    prompt = PromptTemplate.from_template(
        "You are a System Architect creating accurate architecture diagrams using Mermaid.js.\n"
        "You MUST use the EXACT file names, module names, and directory structure provided below.\n"
        "Do NOT invent components that are not visible in the file tree or code context.\n\n"
        "Repository Type: {repository_type}\n"
        "Frameworks: {frameworks}\n"
        "Entry Points: {entry_points}\n\n"
        "=== ACTUAL DIRECTORY STRUCTURE ===\n"
        "{file_tree}\n\n"
        "=== CODE CONTEXT ===\n"
        "{context}\n\n"
        "Generate a Mermaid.js diagram that accurately reflects the real architecture, data flow, or component relationships.\n"
        "Return ONLY valid raw Mermaid code (starting with graph TD or flowchart TD). No extra text.\n\n"
        "Mermaid Diagram:"
    )
    chain = prompt | llm
    res = chain.invoke({
        "repository_type": project.repository_type or "Unknown",
        "frameworks": ", ".join(project.frameworks or []),
        "entry_points": ", ".join(project.entry_points or []),
        "file_tree": file_tree,
        "context": context
    }, config={"callbacks": get_callbacks()})

    # Strip markdown code fences if the model added them
    content = res.content.strip()
    if content.startswith("```"):
        content = "\n".join(content.split("\n")[1:])
    if content.endswith("```"):
        content = "\n".join(content.split("\n")[:-1])
    return content.strip()


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
            db.commit()

        if "PM" in personas:
            project.pm_docs = run_pm_agent(project.id, project, llm)
            db.commit()

        project.architecture_diagram = run_visual_agent(project.id, project, llm)

        project.status = "documented"
        db.commit()
    except Exception as e:
        print(f"Agent Orchestration Failed: {e}")
        project.status = "failed"
        db.commit()
    finally:
        db.close()
