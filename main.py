from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from auth import DUMMY_HASH
from database import engine, get_db
from models import User, Book, IssuedBook
import models
import schemas
from typing import List
from models import Role

from auth import (
    verify_password,
    create_access_token,
    DUMMY_HASH
)

from auth import (
    hash_password,
    verify_password,
    create_access_token,
    verify_token
)

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Library Management System")

security = HTTPBearer()

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    token = credentials.credentials
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = verify_token(token)

    if payload is None:
        raise credentials_exception

    user_id = payload.get("sub")
    role = payload.get("role")

    if user_id is None or role is None:
        raise credentials_exception

    user = db.query(User).filter(
        User.id == int(user_id)
    ).first()

    if user is None:
        raise credentials_exception

    return user

class RoleChecker:
    def __init__(self, allowed_roles: List[Role]):
        self.allowed_roles = [r.value for r in allowed_roles]

    def __call__(
        self,
        current_user: User = Depends(get_current_user)
    ):
        if current_user.role.value not in self.allowed_roles:
            raise HTTPException(
                status_code=403,
                detail="Forbidden"
            )

        return current_user


admin_only = RoleChecker([Role.admin])

student_only = RoleChecker([Role.student])

admin_or_student = RoleChecker([
    Role.admin,
    Role.student
])

@app.post("/register")
def register_user(
    user: schemas.UserCreate,
    db: Session = Depends(get_db)
):
    existing_user = db.query(User).filter(
        User.email == user.email
    ).first()

    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="Email already exists"
        )

    hashed_pwd = hash_password(user.password)

    new_user = User(
        name=user.name,
        email=user.email,
        password=hashed_pwd,
        role=user.role
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {
        "message": "User registered successfully",
        "user": {
            "id": new_user.id,
            "name": new_user.name,
            "email": new_user.email,
            "role": new_user.role
        }
    }


@app.post("/login", response_model=schemas.TokenResponse)
def login_user(
    user: schemas.UserLogin,
    db: Session = Depends(get_db)
):
    db_user = db.query(User).filter(
        User.email == user.email
    ).first()

    if not db_user:
        verify_password(user.password, DUMMY_HASH)

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Email, Password or Role"
        )

    if not verify_password(
        user.password,
        db_user.password
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Email, Password or Role"
        )

    if db_user.role != user.role:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Role"
        )

    access_token = create_access_token(
        data={
            "sub": str(db_user.id),
            "role": db_user.role.value
        }
    )
    return {
        "access_token": access_token,
        "token_type": "bearer"
    }

@app.get("/me", response_model=schemas.UserResponse)
def get_profile(
    current_user: User = Depends(get_current_user)
):
    return current_user

@app.post("/books")
def add_book(
    book: schemas.BookCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only)
):
    new_book = Book(
        title=book.title,
        author=book.author,
        quantity=book.quantity
    )

    db.add(new_book)
    db.commit()
    db.refresh(new_book)

    return {
        "message": "Book added successfully",
        "book": {
            "id": new_book.id,
            "title": new_book.title,
            "author": new_book.author,
            "quantity": new_book.quantity
        }
    }

@app.get("/books")
def get_books(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    books = db.query(Book).all()

    return books

@app.delete("/book/{book_id}")
def delete_book(
    book_id: int,
    db: Session = Depends(get_db),
   current_user: User = Depends(admin_only)
):
    book = db.query(Book).filter(
        Book.id == book_id
    ).first()

    if not book:
        raise HTTPException(
            status_code=404,
            detail="Book not found"
        )

    db.delete(book)
    db.commit()

    return {
        "message": "Book Deleted Successfully"
    }

@app.post("/issue_book")
def issue_book(
    data: schemas.IssueBook,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    user = db.query(User).filter(
        User.id == data.user_id
    ).first()

    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    book = db.query(Book).filter(
        Book.id == data.book_id
    ).first()

    if not book:
        raise HTTPException(
            status_code=404,
            detail="Book not found"
        )

    if book.quantity <= 0:
        raise HTTPException(
            status_code=400,
            detail="Book out of stock"
        )

    already_issued = db.query(IssuedBook).filter(
        IssuedBook.user_id == data.user_id,
        IssuedBook.book_id == data.book_id
    ).first()

    if already_issued:
        raise HTTPException(
            status_code=400,
            detail="Book already issued by this user"
        )

    issued_count = db.query(IssuedBook).filter(
        IssuedBook.user_id == data.user_id
    ).count()

    if issued_count >= 5:
        raise HTTPException(
            status_code=400,
            detail="User cannot issue more than 5 books"
        )

    issue_entry = IssuedBook(
        user_id=data.user_id,
        book_id=data.book_id
    )

    book.quantity -= 1

    db.add(issue_entry)
    db.commit()
    db.refresh(issue_entry)

    return {
        "message": "Book Issued Successfully",
        "issue_id": issue_entry.id
    }

@app.post("/return-book")
def return_book(
    data: schemas.ReturnBook,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    issue_book = db.query(IssuedBook).filter(
        IssuedBook.user_id == data.user_id,
        IssuedBook.book_id == data.book_id
    ).first()

    if not issue_book:
        raise HTTPException(
            status_code=404,
            detail="Issued book detail not found"
        )

    book = db.query(Book).filter(
        Book.id == data.book_id
    ).first()

    if not book:
        raise HTTPException(
            status_code=404,
            detail="Book not found"
        )

    book.quantity += 1

    db.delete(issue_book)
    db.commit()

    return {
        "message": "Book Returned Successfully"
    }

@app.get("/issued-books")
def get_issued_books(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    issued_books = db.query(IssuedBook).all()

    result = []

    for issue in issued_books:
        result.append({
            "issue_id": issue.id,
            "user_id": issue.user.id,
            "user_name": issue.user.name,
            "book_id": issue.book.id,
            "book_title": issue.book.title,
            "author": issue.book.author
        })

    return result