import os
import zipfile
import uuid
import re
import aiofiles
from datetime import timedelta
from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, Form, BackgroundTasks
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from jose import jwt, JWTError
from pydantic import BaseModel
from database import get_db, User, Project
from schemas import UserCreate, UserInDB, Token, TokenData, ProjectInfo, ProjectCreateGitHub
from security import verify_password, get_password_hash, create_access_token, SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
from fastapi.responses import FileResponse
from processor import process_project_background, search_code
from agents import generate_documentation_background, fetch_context_from_chroma, get_callbacks
from export_service import convert_markdown_to_pdf
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate

app = FastAPI(title="Multi-Agent Code Analysis & Documentation System API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

def get_current_user(db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
        token_data = TokenData(email=email)
    except JWTError:
        raise credentials_exception
        
    user = db.query(User).filter(User.email == token_data.email).first()
    if user is None:
        raise credentials_exception
    return user

# AUTH ROUTES
@app.post("/api/auth/register", response_model=UserInDB)
def register(user_in: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == user_in.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
        
    hashed_password = get_password_hash(user_in.password)
    db_user = User(email=user_in.email, hashed_password=hashed_password, role=user_in.role)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

@app.post("/api/auth/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
        
    access_token = create_access_token(
        subject=user.email, 
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    return {"access_token": access_token, "token_type": "bearer"}

# USER PROFILE ROUTES
@app.get("/api/users/me")
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "email": current_user.email,
        "role": current_user.role
    }

# ADMIN ROUTES
@app.get("/api/admin/metrics")
def get_admin_metrics(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Forbidden: You are not an admin.")
        
    total_users = db.query(User).count()
    total_projects = db.query(Project).count()
    documented = db.query(Project).filter(Project.status == "documented").count()
    globals_p = db.query(Project).order_by(Project.id.desc()).limit(15).all()
    
    return {
        "total_users": total_users,
        "total_projects": total_projects,
        "documented": documented,
        "recent_projects": globals_p
    }

@app.get("/api/admin/users", response_model=list[UserInDB])
def get_all_users(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    return db.query(User).all()

@app.delete("/api/admin/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    if current_user.id == user_id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    db.delete(user)
    db.commit()
    return {"status": "deleted"}

@app.get("/api/admin/projects", response_model=list[ProjectInfo])
def get_all_projects(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    return db.query(Project).all()

@app.delete("/api/admin/projects/{project_id}")
def delete_admin_project(project_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    db.delete(project)
    db.commit()
    return {"status": "deleted"}

# PROJECT ROUTES
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.post("/api/projects/upload", response_model=ProjectInfo)
async def upload_project(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    personas: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    print(f"DEBUG: Received ZIP upload request. Filename: {file.filename}, User ID: {current_user.id}")
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(status_code=500, detail="The server is missing the OPENAI_API_KEY environment variable.")
        
    personas_list = [p.strip() for p in personas.split(",") if p.strip()]
    if not personas_list:
        raise HTTPException(status_code=400, detail="At least one persona must be selected")
        
    if not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Must be a .zip file")

    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)
    
    if file_size > (100 * 1024 * 1024):
        raise HTTPException(status_code=400, detail="File too large (Max 100MB)")

    temp_id = str(uuid.uuid4())
    temp_zip_path = os.path.join(UPLOAD_DIR, f"{temp_id}.zip")
    extract_path = os.path.join(UPLOAD_DIR, temp_id)
    
    try:
        async with aiofiles.open(temp_zip_path, 'wb') as out_file:
            content = await file.read()
            await out_file.write(content)
            
        try:
            with zipfile.ZipFile(temp_zip_path, 'r') as zip_ref:
                if not zip_ref.namelist():
                    raise HTTPException(status_code=400, detail="ZIP is empty")
                zip_ref.extractall(extract_path)
        except zipfile.BadZipFile:
            raise HTTPException(status_code=400, detail="Corrupted ZIP file")
    finally:
        if os.path.exists(temp_zip_path):
            os.remove(temp_zip_path)

    project = Project(
        name=file.filename,
        source_type="zip",
        file_path=extract_path,
        status="created",
        personas=personas_list,
        user_id=current_user.id
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    
    background_tasks.add_task(process_project_background, project.id)
    
    return project

@app.post("/api/projects/github", response_model=ProjectInfo)
def add_github_project(
    background_tasks: BackgroundTasks,
    project_in: ProjectCreateGitHub,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    print(f"DEBUG: Received GitHub project request. URL: {project_in.github_url}, User ID: {current_user.id}")
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(status_code=500, detail="The server is missing the OPENAI_API_KEY environment variable.")
        
    if not project_in.personas:
        raise HTTPException(status_code=400, detail="At least one persona required")
        
    if not re.match(r'^https?://github\.com/[\w-]+/[\w.-]+/?$', project_in.github_url):
        raise HTTPException(status_code=400, detail="Malformed GitHub URL")
        
    project = Project(
        name=project_in.github_url.split("/")[-1],
        source_type="github",
        github_url=project_in.github_url,
        status="created",
        personas=project_in.personas,
        user_id=current_user.id
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    
    background_tasks.add_task(process_project_background, project.id)
    
    return project

@app.get("/api/projects/", response_model=list[ProjectInfo])
def get_user_projects(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return db.query(Project).filter(Project.user_id == current_user.id).order_by(Project.id.desc()).all()

# CONTROL ROUTES
@app.post("/api/projects/{project_id}/pause")
def pause_project(project_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    project = db.query(Project).filter(Project.id == project_id, Project.user_id == current_user.id).first()
    if project and project.status in ["analyzing", "generating", "created"]:
        project.status = "paused"
        db.commit()
    return {"status": "paused"}

@app.post("/api/projects/{project_id}/resume")
def resume_project(project_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    project = db.query(Project).filter(Project.id == project_id, Project.user_id == current_user.id).first()
    if project and project.status == "paused":
        if not project.repository_type:
            project.status = "created"
            db.commit()
            background_tasks.add_task(process_project_background, project.id)
        else:
            project.status = "completed"
            db.commit()
            background_tasks.add_task(generate_documentation_background, project.id)
    return {"status": "resumed"}

# INTELLIGENT SEARCH
class SearchQuery(BaseModel):
    query: str

@app.post("/api/projects/{project_id}/search")
def run_search(project_id: int, query: SearchQuery, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(status_code=500, detail="The server is missing the OPENAI_API_KEY environment variable.")
        
    project = db.query(Project).filter(Project.id == project_id, Project.user_id == current_user.id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    results = search_code(project.id, query.query)
    return {"results": results}

@app.post("/api/projects/{project_id}/generate")
def trigger_generation(project_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(status_code=500, detail="The server is missing the OPENAI_API_KEY environment variable.")
        
    project = db.query(Project).filter(Project.id == project_id, Project.user_id == current_user.id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    if project.status not in ["completed", "documented", "failed"]:
        raise HTTPException(status_code=400, detail="Project must be analyzed fully before documentation generation.")
        
    project.status = "generating"
    db.commit()
    
    background_tasks.add_task(generate_documentation_background, project.id)
    return {"status": "started", "message": "Agents are currently generating the documentation."}

class ChatPayload(BaseModel):
    query: str

@app.post("/api/projects/{project_id}/chat")
def project_qna(project_id: int, payload: ChatPayload, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    project = db.query(Project).filter(Project.id == project_id, Project.user_id == current_user.id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    if project.status in ["paused", "analyzing", "generating", "created"]:
        project.analysis_context += f"\nUSER INSTRUCTION: {payload.query}"
        db.commit()
        
    context = fetch_context_from_chroma(project_id, payload.query, k=10)
    
    llm = ChatOpenAI(model="gpt-4o-mini", api_key=os.getenv("OPENAI_API_KEY"), temperature=0.2)
    prompt = PromptTemplate.from_template(
        "You are an expert AI assistant helping a user manage a multi-agent documentation system.\n"
        "If the user is providing instructions (e.g. 'focus on auth'), acknowledge them and state that the agents will use this context.\n"
        "If they are asking about the code, answer using the provided context.\n"
        "Current Project Status: {status}\n\n"
        "Project Frameworks: {frameworks}\n\n"
        "Context:\n{context}\n\n"
        "User Input: {question}\n\n"
        "Response:"
    )
    chain = prompt | llm
    
    res = chain.invoke(
        {"status": project.status, "frameworks": ", ".join(project.frameworks or []), "context": context, "question": payload.query},
        config={"callbacks": get_callbacks()}
    )
    return {"reply": res.content}

@app.get("/api/projects/{project_id}/export/pdf")
def export_project_pdf(project_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    project = db.query(Project).filter(Project.id == project_id, Project.user_id == current_user.id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    if project.status != "documented":
        raise HTTPException(status_code=400, detail="Project must be documented before export.")
        
    full_markdown = f"# {project.name} - Complete Documentation\n\n"
    if project.sde_docs:
        full_markdown += f"## Software Engineer Documentation\n\n{project.sde_docs}\n\n"
    if project.pm_docs:
        full_markdown += f"## Product Manager Documentation\n\n{project.pm_docs}\n\n"
    if project.architecture_diagram:
        full_markdown += f"## Architecture Diagram (Mermaid Source)\n\n```mermaid\n{project.architecture_diagram}\n```\n"

    pdf_filename = f"MACADS_Report_{project_id}.pdf"
    pdf_path = os.path.join(UPLOAD_DIR, pdf_filename)
    
    success = convert_markdown_to_pdf(full_markdown, pdf_path, title=f"MACADS: {project.name}")
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to generate PDF")
        
    return FileResponse(path=pdf_path, filename=pdf_filename, media_type='application/pdf')
