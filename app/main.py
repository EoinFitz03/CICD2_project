# app/main.py

from contextlib import asynccontextmanager
import os  # read environment variables
import httpx  # used to call other microservices over HTTP

from fastapi import FastAPI, Depends, HTTPException, status, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .database import engine, get_db
from .models import Base, UserDB
from .schemas import UserInput, UserOutput, UserUpdate

@asynccontextmanager
async def lifespan(app: FastAPI):
    # This runs once when the service starts
    # It creates the users table if it does not exist yet
    Base.metadata.create_all(bind=engine)
    yield  # after this line, FastAPI starts serving requests


# Create the FastAPI app and attach the lifespan 
app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# These are the addresses for Workout service and Goals service.
# If they are not set, we default to localhost ports for running locally.
WORKOUT_SERVICE_BASE_URL = os.getenv("WORKOUT_SERVICE_BASE_URL", "http://localhost:8001")
GOALS_SERVICE_BASE_URL = os.getenv("GOALS_SERVICE_BASE_URL", "http://localhost:8002")

def commit_or_rollback(db: Session, error_msg: str):
    # This tries to commit changes to the DB.
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,  
            detail=error_msg,
        )


@app.get("/health")
def health():
    # Simple endpoint for checking if service is alive
    return {"status": "ok"}


@app.get("/")
def root():
    # Simple homepage message
    return {"message": "Welcome to the Fitness Tracker Users Service"}

# CREATE a user
@app.post(
    "/api/users",
    response_model=UserOutput,
    status_code=status.HTTP_201_CREATED,
)
def add_user(payload: UserInput, db: Session = Depends(get_db)):
    # Create a user row from the request body
    user = UserDB(**payload.model_dump())
    db.add(user)

    # Save to DB (or rollback if duplicate etc.)
    commit_or_rollback(db, "User already exists")

    db.refresh(user)
    return user


# LIST users 
@app.get("/api/users", response_model=list[UserOutput])
def list_users(
    limit: int = 10,   # how many users to return
    offset: int = 0,   # how many to skip 
    db: Session = Depends(get_db),
):
    # Build a SQL query: ORDER BY user_id, then LIMIT/OFFSET
    stmt = (
        select(UserDB)
        .order_by(UserDB.user_id)
        .limit(limit)
        .offset(offset)
    )

    # Run the query and return the list
    result = db.execute(stmt)
    return result.scalars().all()


# GET one user by ID
@app.get("/api/users/{user_id}", response_model=UserOutput)
def get_user(user_id: int, db: Session = Depends(get_db)):
    # db.get finds by primary key
    user = db.get(UserDB, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return user

@app.put("/api/users/{user_id}", response_model=UserOutput)
def replace_user(
    user_id: int,
    payload: UserInput,
    db: Session = Depends(get_db),
):
    # Find the user first
    user = db.get(UserDB, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Replace ALL fields (PUT is “full update”)
    user.name = payload.name
    user.email = payload.email
    user.age = payload.age
    user.gender = payload.gender

    # Save changes 
    commit_or_rollback(db, "User update failed")
    db.refresh(user)
    return user


# PARTIAL UPDATE user 
@app.patch("/api/users/{user_id}", response_model=UserOutput)
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
):
    # Find the user first
    user = db.get(UserDB, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Only pull the fields the user actually sent (exclude_unset=True)
    data = payload.model_dump(exclude_unset=True)

    # Update those fields only
    for field, value in data.items():
        setattr(user, field, value)

    # Save changes
    commit_or_rollback(db, "User update failed")
    db.refresh(user)
    return user


# DELETE user
@app.delete("/api/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: int, db: Session = Depends(get_db)) -> Response:
    # Find the user first
    user = db.get(UserDB, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Delete from DB
    db.delete(user)
    db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)

# These endpoints let the Users service call the Workout service and Goals service.
# It shows the pattern of one service calling another service.
@app.get("/api/proxy/workouts/{user_id}", tags=["proxy"])
def proxy_workouts(user_id: int, db: Session = Depends(get_db)):
    """
    Proxy endpoint:
    - Check user exists in Users DB
    - Call Workout service to get workouts for that user
    - Return the workout service response
    """
    # First, make sure user exists
    user = db.get(UserDB, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Build the URL to call Workout service
    url = f"{WORKOUT_SERVICE_BASE_URL}/workouts"

    try:
        # Call workout service with user_id as query param
        with httpx.Client() as client:
            res = client.get(url, params={"user_id": user_id})

        res.raise_for_status()

    except httpx.RequestError as exc:
        # Network problem: service down, timeout, bad DNS, etc.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Error contacting workout service: {exc}",
        )

    except httpx.HTTPStatusError as exc:
        # Workout service returned an error status
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Workout service error: {exc.response.text}",
        )

    # Return a small wrapper + the workouts list
    return {
        "from": "user_service",
        "workouts": res.json(),
    }