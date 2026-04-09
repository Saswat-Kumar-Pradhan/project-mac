import os
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, JSON
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./macads.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, default="user") # "user" or "admin"
    
    projects = relationship("Project", back_populates="owner", cascade="all, delete-orphan")

class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    source_type = Column(String, nullable=False)
    file_path = Column(String, nullable=True)
    github_url = Column(String, nullable=True)
    status = Column(String, default="created")
    personas = Column(JSON, nullable=False)
    
    repository_type = Column(String, nullable=True)
    frameworks = Column(JSON, nullable=True)
    entry_points = Column(JSON, nullable=True)
    
    sde_docs = Column(String, nullable=True)
    pm_docs = Column(String, nullable=True)
    architecture_diagram = Column(String, nullable=True)
    analysis_context = Column(String, default="")
    
    user_id = Column(Integer, ForeignKey("users.id"))
    owner = relationship("User", back_populates="projects")

Base.metadata.create_all(bind=engine)
