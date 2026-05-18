from pydantic import BaseModel
from typing import Optional
from enum import Enum

class Role(str, Enum):
    admin = "admin"
    student = "student"

class UserCreate(BaseModel):
    name: str
    email: str
    password: str
    role: Role

class UserLogin(BaseModel):
    email: str
    password: str
    role: Role

class BookCreate(BaseModel):
    title: str
    author: str
    quantity: int

class IssueBook(BaseModel):
    user_id: int
    book_id: int

class ReturnBook(BaseModel):
    user_id: int
    book_id: int

class TokenResponse(BaseModel):
    access_token: str
    token_type: str

class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    role: Role

    class Config:
        from_attributes = True