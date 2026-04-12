import os
import json
import zipfile
import shutil
import uuid
import subprocess
import chromadb
from chroma import get_chroma_client
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from langchain_core.prompts import PromptTemplate
from database import SessionLocal, Project, AnalysisLog
from sqlalchemy.orm import Session
from langfuse.callback import CallbackHandler

def add_log(db: Session, project_id: int, message: str, percentage: int = 0, level: str = "info"):
    log = AnalysisLog(project_id=project_id, message=message, percentage=percentage, level=level)
    db.add(log)
    db.commit()
    print(f"[PROJECT {project_id}][{percentage}%] {message}")

def get_callbacks():
    if os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"):
        return [CallbackHandler(
            public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
            secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
            host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
        )]
    return []

def process_project_background(project_id: int):
    db: Session = SessionLocal()
    project = db.query(Project).filter(Project.id == project_id).first()
    
    if not project:
        db.close()
        return

    # Clear old logs for fresh analysis
    db.query(AnalysisLog).filter(AnalysisLog.project_id == project_id).delete()
    db.commit()

    add_log(db, project_id, "Initializing analysis pipeline...", 5)
        
    if project.source_type == "github" and not project.file_path:
        upload_dir = os.path.join(os.path.dirname(__file__), "uploads")
        os.makedirs(upload_dir, exist_ok=True)
        temp_id = str(uuid.uuid4())
        extract_path = os.path.join(upload_dir, temp_id)
        
        try:
            add_log(db, project_id, f"Cloning repository: {project.github_url}", 10)
            subprocess.run(["git", "clone", "--depth", "1", project.github_url, extract_path], check=True)
            project.file_path = extract_path
            db.commit()
            add_log(db, project_id, "Cloning complete.", 15)
        except Exception as e:
            msg = f"Failed to clone repository: {e}"
            add_log(db, project_id, msg, level="error")
            project.status = "failed"
            db.commit()
            db.close()
            return

    if not project.file_path:
        db.close()
        return
        
    project.status = "analyzing"
    db.commit()
    add_log(db, project_id, "Starting filesystem deep scan...", 20)

    try:
        docs = []
        file_tree = []
        skip_dirs = {".git", "node_modules", "venv", "__pycache__", ".next", "dist", "build"}
        skip_exts = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".mp4", ".pdf", ".zip", ".sqlite3", ".db"}
        
        total_files = sum([len(files) for r, d, files in os.walk(project.file_path)])
        files_processed = 0
        last_log_time = 0
        
        for root, dirs, files in os.walk(project.file_path):
            dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".")]
            
            for file in files:
                files_processed += 1
                ext = os.path.splitext(file)[1].lower()
                rel_path = os.path.relpath(os.path.join(root, file), project.file_path)
                
                if ext in skip_exts or file.startswith("."):
                    continue
                
                full_path = os.path.join(root, file)
                file_tree.append(rel_path)
                
                # Update progress percentage (20% to 35% during scan)
                scan_percentage = 20 + int((files_processed / total_files) * 15)
                
                # Throttle logging to avoid DB bloat: log every file if < 50 files, else every 5 files or every 0.5s
                import time
                if total_files < 50 or files_processed % 5 == 0 or (time.time() - last_log_time) > 0.5:
                    add_log(db, project_id, f"Analyzing: {rel_path}", scan_percentage)
                    last_log_time = time.time()
                
                try:
                    with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                        if content.strip():
                            docs.append(Document(page_content=content, metadata={"source": rel_path}))
                except Exception:
                    add_log(db, project_id, f"Skipped unreadable file: {rel_path}", scan_percentage, level="warning")
                    pass

        add_log(db, project_id, f"Scan complete. Found {len(file_tree)} files and {len(docs)} text documents.", 35)

        if not file_tree:
            project.status = "failed"
            db.commit()
            return
            
        tree_str = "\n".join(file_tree[:300])  # store up to 300 paths

        # Persist the file tree so agents can use it for accurate docs
        project.file_tree = tree_str
        db.commit()
        
        db.refresh(project)
        if project.status == "paused": 
            return
            
        try:
            llm = ChatOpenAI(model="gpt-4o-mini", api_key=os.getenv("OPENAI_API_KEY"), temperature=0.1)
            prompt = PromptTemplate.from_template(
                "Analyze the following file tree of a code repository and identify its type, main frameworks, and entry points.\n"
                "Return EXACTLY a JSON dictionary with keys 'repository_type' (string), 'frameworks' (list of strings), and 'entry_points' (list of strings).\n\n"
                "File Tree:\n{tree}"
            )
            
            chain = prompt | llm
            res = chain.invoke({"tree": tree_str}, config={"callbacks": get_callbacks()})
            
            json_text = res.content.strip()
            if json_text.startswith("```json"): json_text = json_text[7:]
            if json_text.endswith("```"): json_text = json_text[:-3]
            data = json.loads(json_text)
            
            project.repository_type = data.get("repository_type")
            project.frameworks = data.get("frameworks", [])
            project.entry_points = data.get("entry_points", [])
            add_log(db, project_id, f"Architecture identified: {project.repository_type}", 45)
        except Exception as e:
            add_log(db, project_id, f"LLM analysis failed: {e}", level="warning")
            
        add_log(db, project_id, "Splitting code into logical chunks...", 50)
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        chunks = text_splitter.split_documents(docs)
        add_log(db, project_id, f"Prepared {len(chunks)} contextual code sections.", 55)
        
        db.refresh(project)
        if project.status == "paused":
            return
            
        if chunks:
            try:
                embeddings = OpenAIEmbeddings(api_key=os.getenv("OPENAI_API_KEY"))
                collection_name = f"project_{project.id}"
                try:
                    get_chroma_client().delete_collection(name=collection_name)
                except Exception:
                    pass

                collection = get_chroma_client().create_collection(name=collection_name)
                
                ids = [f"chunk_{i}" for i in range(len(chunks))]
                texts = [c.page_content for c in chunks]
                metadatas = [c.metadata for c in chunks]
                
                add_log(db, project_id, "Starting vector embedding generation...", 60)
                total_batches = (len(texts) + 99) // 100
                for i in range(0, len(texts), 100):
                    batch_num = (i // 100) + 1
                    percentage = 60 + int((batch_num / total_batches) * 35)
                    add_log(db, project_id, f"Embedding batch {batch_num}/{total_batches}...", percentage)
                    
                    collection.add(
                        documents=texts[i:i+100],
                        metadatas=metadatas[i:i+100],
                        ids=ids[i:i+100]
                    )
            except Exception as e:
                add_log(db, project_id, f"Vector storage failed: {e}", level="error")
                
        add_log(db, project_id, "Preprocessing complete. Project ready for AI agents.", 100)
        project.status = "completed"
        db.commit()
        
    except Exception as e:
        print("Error processing project:", e)
        project.status = "failed"
        db.commit()
    finally:
        db.close()

def search_code(project_id: int, query: str):
    try:
        embeddings = OpenAIEmbeddings(api_key=os.getenv("OPENAI_API_KEY"))
        collection = get_chroma_client().get_collection(name=f"project_{project_id}")
        
        query_embedding = embeddings.embed_query(query)
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=5
        )
        
        if not results['documents']:
            return []
            
        formatted_results = []
        for i in range(len(results['documents'][0])):
            formatted_results.append({
                "source": results['metadatas'][0][i].get('source', 'Unknown'),
                "content": results['documents'][0][i],
                "score": results['distances'][0][i] if 'distances' in results else 0
            })
        return formatted_results
    except Exception as e:
        print(f"Search failed: {e}")
        return []
