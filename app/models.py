from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Date, Time, DateTime
from sqlalchemy.orm import relationship

from app.database import Base


class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, nullable=False)
    department = Column(String, nullable=False)
    position = Column(String, nullable=False)
    card_id = Column(String, unique=True, nullable=False)
    is_active = Column(Boolean, default=True)

    schedules = relationship("WorkSchedule", back_populates="employee")
    access_events = relationship("AccessEvent", back_populates="employee")
    violations = relationship("Violation", back_populates="employee")


class WorkSchedule(Base):
    __tablename__ = "work_schedules"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    work_date = Column(Date, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)

    employee = relationship("Employee", back_populates="schedules")
    violations = relationship("Violation", back_populates="schedule")


class AccessEvent(Base):
    __tablename__ = "access_events"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    card_id = Column(String, nullable=False)
    event_time = Column(DateTime, nullable=False)
    direction = Column(String, nullable=False)

    employee = relationship("Employee", back_populates="access_events")


class Violation(Base):
    __tablename__ = "violations"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    schedule_id = Column(Integer, ForeignKey("work_schedules.id"), nullable=False)

    violation_type = Column(String, nullable=False)
    work_date = Column(Date, nullable=False)

    planned_start_time = Column(DateTime, nullable=False)
    actual_entry_time = Column(DateTime, nullable=True)

    late_minutes = Column(Integer, nullable=True)
    status = Column(String, default="Новое")
    screenshot_path = Column(String, nullable=True)

    employee = relationship("Employee", back_populates="violations")
    schedule = relationship("WorkSchedule", back_populates="violations")