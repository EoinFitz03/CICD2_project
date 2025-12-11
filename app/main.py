# app/main.py

from contextlib import asynccontextmanager
import os  # NEW: for reading environment variables
import httpx  # NEW: for calling the other microservices over HTTP

from fastapi import FastAPI, Depends, HTTPException, status, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .database import engine, get_db
from .models import Base, UserDB
from .schemas import UserInput, UserOutput, UserUpdate


# ========= Lifespan / app setup =========

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create the users table on startup
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========= Base URLs for other microservices (NEW) =========
# These follow the pattern from the lab: one env var per downstream service.
# In Docker, you'll set them to e.g. http://workout_service:8000, http://goals_service:8000
# In dev, we fall back to localhost with different ports.
WORKOUT_SERVICE_BASE_URL = os.getenv("WORKOUT_SERVICE_BASE_URL", "http://localhost:8001")
GOALS_SERVICE_BASE_URL = os.getenv("GOALS_SERVICE_BASE_URL", "http://localhost:8002")


# ========= Helper for committing =========

def commit_or_rollback(db: Session, error_msg: str):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error_msg,
        )


# ========= Health & root =========

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def root():
    return {"message": "Welcome to the Fitness Tracker Users Service"}


# ========= Users CRUD =========

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
    return result.scalars().all()


# GET single user by user_id
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


# ========= Integration with other microservices (NEW) =========
# These endpoints show the "Service B calls Service A" pattern from the lab,
# but adapted so the USER service can talk to:
#   - Workout service (/workouts)
#   - Goals service   (/goals)


@app.get("/api/proxy/workouts/{user_id}", tags=["proxy"])
def proxy_workouts(user_id: int, db: Session = Depends(get_db)):
    """
    Simple proxy endpoint:
    - Checks the user exists locally
    - Calls the Workout service: GET /workouts?user_id={user_id}
    - Returns whatever the Workout service responded with
    """
    user = db.get(UserDB, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    url = f"{WORKOUT_SERVICE_BASE_URL}/workouts"

    try:
        with httpx.Client() as client:
            res = client.get(url, params={"user_id": user_id})
        res.raise_for_status()
    except httpx.RequestError as exc:
        # Network error: service down, DNS issue, timeout, etc.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Error contacting workout service: {exc}",
        )
    except httpx.HTTPStatusError as exc:
        # Workout service returned 4xx/5xx
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Workout service error: {exc.response.text}",
        )

    return {
        "from": "user_service",
        "workouts": res.json(),
    }


@app.get("/api/proxy/goals/{user_id}", tags=["proxy"])
def proxy_goals(user_id: int, db: Session = Depends(get_db)):
    """
    Simple proxy endpoint:
    - Checks the user exists locally
    - Calls the Goals service: GET /goals?user_id={user_id}
    - Returns whatever the Goals service responded with
    """
    user = db.get(UserDB, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    url = f"{GOALS_SERVICE_BASE_URL}/goals"

    try:
        with httpx.Client() as client:
            res = client.get(url, params={"user_id": user_id})
        res.raise_for_status()
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Error contacting goals service: {exc}",
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Goals service error: {exc.response.text}",
        )

    return {
        "from": "user_service",
        "goals": res.json(),
    }


@app.get("/api/user-summary/{user_id}", tags=["proxy"])
def user_summary(user_id: int, db: Session = Depends(get_db)):
    """
    Aggregator endpoint:
    - Verifies the user exists in the Users DB
    - Calls Workout service and Goals service using httpx and env-configured base URLs
    - Returns a single combined JSON payload

    This demonstrates the pattern:
    User service = "Service B"
    Workout/Goals services = "Service A" style downstream services.
    """
    user = db.get(UserDB, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    workout_url = f"{WORKOUT_SERVICE_BASE_URL}/workouts"
    goals_url = f"{GOALS_SERVICE_BASE_URL}/goals"

    try:
        with httpx.Client() as client:
            workout_res = client.get(workout_url, params={"user_id": user_id})
            goals_res = client.get(goals_url, params={"user_id": user_id})

        workout_res.raise_for_status()
        goals_res.raise_for_status()

    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Error contacting downstream services: {exc}",
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Downstream service failed: {exc.response.text}",
        )

    workouts = workout_res.json()
    goals = goals_res.json()

    return {
        "user": {
            "user_id": user.user_id,
            "name": user.name,
            "email": user.email,
            "age": user.age,
            "gender": user.gender,
        },
        "workouts": workouts,
        "goals": goals,
    }
