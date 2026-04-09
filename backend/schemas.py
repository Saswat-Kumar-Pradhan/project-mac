from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field

# USER SCHEMAS
class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., max_length=72)
    role: Optional[str] = "user"

class UserInDB(BaseModel):
    id: int
    email: EmailStr
    role: str
    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

# PROJECT SCHEMAS
class ProjectCreateGitHub(BaseModel):
    github_url: str
    personas: List[str]

class ProjectInfo(BaseModel):
    id: int
    name: str
    source_type: str
    status: str
    file_path: Optional[str] = None
    github_url: Optional[str] = None
    personas: List[str]
    repository_type: Optional[str] = None
    frameworks: Optional[List[str]] = None
    entry_points: Optional[List[str]] = None
    
    sde_docs: Optional[str] = None
    pm_docs: Optional[str] = None
    architecture_diagram: Optional[str] = None
    
    class Config:
        from_attributes = True
