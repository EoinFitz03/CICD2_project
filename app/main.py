# app/main.py

from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, status, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .database import engine, get_db
from .models import Base, UserDB
from .schemas import UserInput, UserOutput, UserUpdate


# ---------- Lifespan / app setup ----------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- Helper for committing ----------

def commit_or_rollback(db: Session, error_msg: str):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error_msg,
        )


# ---------- Health & root ----------

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def root():
    return {"message": "Welcome to the Fitness Tracker Users Service"}


# ---------- Users ----------

# CREATE user
@app.post(
    "/api/users",
    response_model=UserOutput,
    status_code=status.HTTP_201_CREATED,
)
def add_user(payload: UserInput, db: Session = Depends(get_db)):
    user = UserDB(**payload.model_dump())
    db.add(user)

    commit_or_rollback(db, "User already exists")
    db.refresh(user)
    return user


# LIST users
@app.get("/api/users", response_model=list[UserOutput])
def list_users(
    limit: int = 10,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    stmt = (
        select(UserDB)
        .order_by(UserDB.user_id)
        .limit(limit)
        .offset(offset)
    )
    result = db.execute(stmt)
    users = result.scalars().all()
    return users


# GET single user
@app.get("/api/users/{user_id}", response_model=UserOutput)
def get_user(user_id: int, db: Session = Depends(get_db)):
    user = db.get(UserDB, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return user


# FULL REPLACE user (PUT)
@app.put("/api/users/{user_id}", response_model=UserOutput)
def replace_user(
    user_id: int,
    payload: UserInput,
    db: Session = Depends(get_db),
):
    user = db.get(UserDB, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    user.name = payload.name
    user.email = payload.email
    user.age = payload.age
    user.gender = payload.gender

    commit_or_rollback(db, "User update failed")
    db.refresh(user)
    return user


# PARTIAL UPDATE user (PATCH)
@app.patch("/api/users/{user_id}", response_model=UserOutput)
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
):
    user = db.get(UserDB, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(user, field, value)

    commit_or_rollback(db, "User update failed")
    db.refresh(user)
    return user


# DELETE user
@app.delete("/api/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: int, db: Session = Depends(get_db)) -> Response:
    user = db.get(UserDB, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    db.delete(user)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
