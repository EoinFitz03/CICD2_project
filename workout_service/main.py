# workout_service/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, status, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
# Reuse the same DB config as your main service
from app.database import engine, get_db

from .models import Base, WorkoutDB
from .schemas import WorkoutCreate, WorkoutRead, WorkoutUpdate


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create workouts table on startup
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)



def commit_or_rollback(db: Session, error_msg: str):
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
    return {"status": "workout service ok"}


@app.get("/")
def root():
    return {"message": "Welcome to the Workout Service"}



# CREATE workout
@app.post("/api/workouts",response_model=WorkoutRead,status_code=status.HTTP_201_CREATED,)
def create_workout(payload: WorkoutCreate, db: Session = Depends(get_db)):
    workout = WorkoutDB(**payload.model_dump())
    db.add(workout)

    commit_or_rollback(db, "Workout creation failed")
    db.refresh(workout)
    return workout


# LIST workouts
@app.get("/api/workouts", response_model=list[WorkoutRead])
def list_workouts(
    user_id: int | None = None,
    limit: int = 10,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    stmt = select(WorkoutDB).order_by(WorkoutDB.id)

    if user_id is not None:
        stmt = stmt.where(WorkoutDB.user_id == user_id)

    stmt = stmt.limit(limit).offset(offset)
    result = db.execute(stmt)
    return result.scalars().all()


# GET single workout
@app.get("/api/workouts/{workout_id}", response_model=WorkoutRead)
def get_workout(workout_id: int, db: Session = Depends(get_db)):
    workout = db.get(WorkoutDB, workout_id)
    if not workout:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workout not found",
        )
    return workout


# FULL REPLACE workout (PUT)
@app.put("/api/workouts/{workout_id}", response_model=WorkoutRead)
def replace_workout(
    workout_id: int,
    payload: WorkoutCreate,
    db: Session = Depends(get_db),
):
    workout = db.get(WorkoutDB, workout_id)
    if not workout:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workout not found",
        )

    workout.name = payload.name
    workout.date = payload.date
    workout.duration_minutes = payload.duration_minutes
    workout.intensity = payload.intensity
    workout.workout_type = payload.workout_type
    workout.notes = payload.notes
    workout.user_id = payload.user_id

    commit_or_rollback(db, "Workout update failed")
    db.refresh(workout)
    return workout


# PARTIAL UPDATE workout (PATCH)
@app.patch("/api/workouts/{workout_id}", response_model=WorkoutRead)
def update_workout(
    workout_id: int,
    payload: WorkoutUpdate,
    db: Session = Depends(get_db),
):
    workout = db.get(WorkoutDB, workout_id)
    if not workout:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workout not found",
        )

    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(workout, field, value)

    commit_or_rollback(db, "Workout update failed")
    db.refresh(workout)
    return workout


# DELETE workout
@app.delete("/api/workouts/{workout_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workout(workout_id: int, db: Session = Depends(get_db)) -> Response:
    workout = db.get(WorkoutDB, workout_id)
    if not workout:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workout not found",
        )

    db.delete(workout)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
