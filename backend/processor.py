import os
import json
import zipfile
import shutil
import uuid
import subprocess
import chromadb
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from langchain_core.prompts import PromptTemplate
from database import SessionLocal, Project
from sqlalchemy.orm import Session
from langfuse.callback import CallbackHandler

CHROMA_PATH = os.path.join(os.path.dirname(__file__), "chroma_db")
chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)

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
        
    if project.source_type == "github" and not project.file_path:
        upload_dir = os.path.join(os.path.dirname(__file__), "uploads")
        os.makedirs(upload_dir, exist_ok=True)
        temp_id = str(uuid.uuid4())
        extract_path = os.path.join(upload_dir, temp_id)
        
        try:
            print(f"Cloning GitHub repository: {project.github_url} into {extract_path}")
            subprocess.run(["git", "clone", "--depth", "1", project.github_url, extract_path], check=True)
            project.file_path = extract_path
            db.commit()
        except Exception as e:
            print(f"Failed to clone repository: {e}")
            project.status = "failed"
            db.commit()
            db.close()
            return

    if not project.file_path:
        db.close()
        return
        
    project.status = "analyzing"
    db.commit()

    try:
        docs = []
        file_tree = []
        skip_dirs = {".git", "node_modules", "venv", "__pycache__", ".next", "dist", "build"}
        skip_exts = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".mp4", ".pdf", ".zip", ".sqlite3", ".db"}
        
        for root, dirs, files in os.walk(project.file_path):
            dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".")]
            
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in skip_exts or file.startswith("."):
                    continue
                
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, project.file_path)
                file_tree.append(rel_path)
                
                try:
                    with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                        if content.strip():
                            docs.append(Document(page_content=content, metadata={"source": rel_path}))
                except Exception:
                    pass

        if not file_tree:
            project.status = "failed"
            db.commit()
            return
            
        tree_str = "\n".join(file_tree[:150])
        
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
        except Exception as e:
            print(f"OpenAI LLM processing failed: {e}")
            
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        chunks = text_splitter.split_documents(docs)
        
        db.refresh(project)
        if project.status == "paused":
            return
            
        if chunks:
            try:
                embeddings = OpenAIEmbeddings(api_key=os.getenv("OPENAI_API_KEY"))
                collection_name = f"project_{project.id}"
                
                try:
                    chroma_client.delete_collection(name=collection_name)
                except Exception:
                    pass
                
                collection = chroma_client.create_collection(name=collection_name)
                
                ids = [f"chunk_{i}" for i in range(len(chunks))]
                texts = [c.page_content for c in chunks]
                metadatas = [c.metadata for c in chunks]
                
                for i in range(0, len(texts), 100):
                    collection.add(
                        documents=texts[i:i+100],
                        metadatas=metadatas[i:i+100],
                        ids=ids[i:i+100]
                    )
            except Exception as e:
                print(f"ChromaDB embedding failed: {e}")
                
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
        collection = chroma_client.get_collection(name=f"project_{project_id}")
        
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
