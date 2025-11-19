# app/models.py

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Integer, Enum as SAEnum

from .schemas import GenderEnum


class Base(DeclarativeBase):
    pass


class UserDB(Base):
    __tablename__ = "users"

  
    user_id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    gender: Mapped[GenderEnum] = mapped_column(
        SAEnum(GenderEnum, name="gender_enum"),
        nullable=False,
    )
