# workout_service/models.py
from typing import Optional
from datetime import date
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Integer, Date, Enum as SAEnum, ForeignKey
from .schemas import IntensityEnum, WorkoutTypeEnum

class Base(DeclarativeBase):
    pass


class WorkoutDB(Base):
    __tablename__ = "workouts"
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    # Link to user in the users service 
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)

    intensity: Mapped[IntensityEnum] = mapped_column(
        SAEnum(IntensityEnum, name="workout_intensity_enum"),
        nullable=False,
    )

    workout_type: Mapped[WorkoutTypeEnum] = mapped_column(
        SAEnum(WorkoutTypeEnum, name="workout_type_enum"),
        nullable=False,
    )

    notes: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    calories_burned: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
