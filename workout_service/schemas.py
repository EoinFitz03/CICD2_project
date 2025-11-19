from typing import Annotated, Optional
from enum import Enum
from datetime import date

from annotated_types import Ge, Le
from pydantic import BaseModel, ConfigDict, StringConstraints


# ---------- Reusable type aliases ----------

WorkoutNameStr = Annotated[str, StringConstraints(min_length=1, max_length=100)]
DescStr        = Annotated[str, StringConstraints(min_length=0, max_length=1000)]

DurationMinInt = Annotated[int, Ge(1), Le(600)]     # between 1 and 600 mins
CaloriesInt    = Annotated[int, Ge(0), Le(10000)]   # cap for sanity
UserIdInt      = int


class IntensityEnum(str, Enum):
    low    = "low"
    medium = "medium"
    high   = "high"


class WorkoutTypeEnum(str, Enum):
    cardio   = "cardio"
    strength = "strength"
    mobility = "mobility"
    mixed    = "mixed"
    other    = "other"


class WorkoutBase(BaseModel):
    name: WorkoutNameStr
    date: date
    duration_minutes: DurationMinInt
    intensity: IntensityEnum
    workout_type: WorkoutTypeEnum = WorkoutTypeEnum.other
    notes: Optional[DescStr] = None


# Create / Read / Update 

# Request body when creating a workout
class WorkoutCreate(WorkoutBase):
    # Link to user in the user service
    user_id: UserIdInt


# 
class WorkoutRead(WorkoutBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: UserIdInt
    calories_burned: Optional[CaloriesInt] = None


# PATCH
class WorkoutUpdate(BaseModel):
    name: Optional[WorkoutNameStr] = None
    date: Optional[date] = None
    duration_minutes: Optional[DurationMinInt] = None
    intensity: Optional[IntensityEnum] = None
    workout_type: Optional[WorkoutTypeEnum] = None
    notes: Optional[DescStr] = None
    calories_burned: Optional[CaloriesInt] = None
