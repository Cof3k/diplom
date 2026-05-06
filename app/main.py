from datetime import date, time, datetime, timedelta
from fastapi import FastAPI, Depends, HTTPException, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import Base, engine, SessionLocal
from app.models import Employee, WorkSchedule, AccessEvent, Violation

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Система контроля опозданий сотрудников больницы")
templates = Jinja2Templates(directory="app/templates")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/")
def read_root():
    return {
        "message": "Система контроля опозданий сотрудников больницы работает"
    }


@app.post("/employees")
def create_employee(
    full_name: str,
    department: str,
    position: str,
    card_id: str,
    db: Session = Depends(get_db)
):
    employee = Employee(
        full_name=full_name,
        department=department,
        position=position,
        card_id=card_id
    )

    db.add(employee)
    db.commit()
    db.refresh(employee)

    return employee


@app.get("/employees")
def get_employees(db: Session = Depends(get_db)):
    employees = db.query(Employee).all()
    return employees

@app.post("/schedules")
def create_schedule(
    employee_id: int,
    work_date: date,
    start_time: time,
    end_time: time,
    db: Session = Depends(get_db)
):
    employee = db.query(Employee).filter(Employee.id == employee_id).first()

    if not employee:
        raise HTTPException(
            status_code=404,
            detail="Сотрудник не найден"
        )

    schedule = WorkSchedule(
        employee_id=employee_id,
        work_date=work_date,
        start_time=start_time,
        end_time=end_time
    )

    db.add(schedule)
    db.commit()
    db.refresh(schedule)

    return schedule


@app.get("/schedules")
def get_schedules(db: Session = Depends(get_db)):
    schedules = db.query(WorkSchedule).all()
    return schedules

@app.post("/access-events")
def create_access_event(
    card_id: str,
    event_time: datetime,
    direction: str,
    db: Session = Depends(get_db)
):
    employee = db.query(Employee).filter(Employee.card_id == card_id).first()

    if not employee:
        raise HTTPException(
            status_code=404,
            detail="Сотрудник с такой картой не найден"
        )

    access_event = AccessEvent(
        employee_id=employee.id,
        card_id=card_id,
        event_time=event_time,
        direction=direction
    )

    db.add(access_event)
    db.commit()
    db.refresh(access_event)

    return access_event


@app.get("/access-events")
def get_access_events(db: Session = Depends(get_db)):
    events = db.query(AccessEvent).all()
    return events

@app.post("/check-lateness")
def check_lateness(
    work_date: date,
    grace_period_minutes: int = 5,
    db: Session = Depends(get_db)
):
    schedules = db.query(WorkSchedule).filter(
        WorkSchedule.work_date == work_date
    ).all()

    created_violations = []

    for schedule in schedules:
        planned_start = datetime.combine(schedule.work_date, schedule.start_time)
        allowed_start = planned_start + timedelta(minutes=grace_period_minutes)

        first_entry = db.query(AccessEvent).filter(
            AccessEvent.employee_id == schedule.employee_id,
            AccessEvent.direction == "IN",
            AccessEvent.event_time >= planned_start.replace(hour=0, minute=0, second=0),
            AccessEvent.event_time <= planned_start.replace(hour=23, minute=59, second=59)
        ).order_by(AccessEvent.event_time.asc()).first()

        if not first_entry:
            continue

        if first_entry.event_time > allowed_start:
            existing_violation = db.query(Violation).filter(
                Violation.employee_id == schedule.employee_id,
                Violation.schedule_id == schedule.id,
                Violation.violation_type == "Опоздание"
            ).first()

            if existing_violation:
                continue

            late_minutes = int((first_entry.event_time - allowed_start).total_seconds() // 60)

            violation = Violation(
                employee_id=schedule.employee_id,
                schedule_id=schedule.id,
                violation_type="Опоздание",
                work_date=schedule.work_date,
                planned_start_time=planned_start,
                actual_entry_time=first_entry.event_time,
                late_minutes=late_minutes,
                status="Новое",
                screenshot_path=None
            )

            db.add(violation)
            created_violations.append(violation)

    db.commit()

    for violation in created_violations:
        db.refresh(violation)

    return {
        "message": "Проверка опозданий выполнена",
        "created_count": len(created_violations),
        "violations": created_violations
    }


@app.get("/violations")
def get_violations(db: Session = Depends(get_db)):
    violations = db.query(Violation).all()
    return violations

@app.post("/check-absences")
def check_absences(
    work_date: date,
    db: Session = Depends(get_db)
):
    schedules = db.query(WorkSchedule).filter(
        WorkSchedule.work_date == work_date
    ).all()

    created_violations = []

    for schedule in schedules:
        planned_start = datetime.combine(schedule.work_date, schedule.start_time)

        day_start = planned_start.replace(hour=0, minute=0, second=0)
        day_end = planned_start.replace(hour=23, minute=59, second=59)

        first_entry = db.query(AccessEvent).filter(
            AccessEvent.employee_id == schedule.employee_id,
            AccessEvent.direction == "IN",
            AccessEvent.event_time >= day_start,
            AccessEvent.event_time <= day_end
        ).order_by(AccessEvent.event_time.asc()).first()

        if first_entry:
            continue

        existing_violation = db.query(Violation).filter(
            Violation.employee_id == schedule.employee_id,
            Violation.schedule_id == schedule.id,
            Violation.violation_type == "Неявка"
        ).first()

        if existing_violation:
            continue

        violation = Violation(
            employee_id=schedule.employee_id,
            schedule_id=schedule.id,
            violation_type="Неявка",
            work_date=schedule.work_date,
            planned_start_time=planned_start,
            actual_entry_time=None,
            late_minutes=None,
            status="Новое",
            screenshot_path=None
        )

        db.add(violation)
        created_violations.append(violation)

    db.commit()

    for violation in created_violations:
        db.refresh(violation)

    return {
        "message": "Проверка неявок выполнена",
        "created_count": len(created_violations),
        "violations": created_violations
    }

@app.get("/dashboard")
def dashboard(request: Request, db: Session = Depends(get_db)):
    employees_count = db.query(Employee).count()
    schedules_count = db.query(WorkSchedule).count()
    access_events_count = db.query(AccessEvent).count()
    violations_count = db.query(Violation).count()

    latest_violations = db.query(Violation).order_by(
        Violation.id.desc()
    ).limit(10).all()

    return templates.TemplateResponse(
    request=request,
    name="dashboard.html",
    context={
        "employees_count": employees_count,
        "schedules_count": schedules_count,
        "access_events_count": access_events_count,
        "violations_count": violations_count,
        "latest_violations": latest_violations,
    }
)

@app.get("/employees-page")
def employees_page(request: Request, db: Session = Depends(get_db)):
    employees = db.query(Employee).order_by(Employee.id.asc()).all()

    return templates.TemplateResponse(
        request=request,
        name="employees.html",
        context={
            "employees": employees
        }
    )

@app.get("/violations-page")
def violations_page(request: Request, db: Session = Depends(get_db)):
    violations = db.query(Violation).order_by(
        Violation.id.desc()
    ).all()

    return templates.TemplateResponse(
        request=request,
        name="violations.html",
        context={
            "violations": violations
        }
    )

@app.get("/schedules-page")
def schedules_page(request: Request, db: Session = Depends(get_db)):
    schedules = db.query(WorkSchedule).order_by(
        WorkSchedule.work_date.desc(),
        WorkSchedule.start_time.asc()
    ).all()

    employees = db.query(Employee).order_by(Employee.full_name.asc()).all()

    return templates.TemplateResponse(
        request=request,
        name="schedules.html",
        context={
            "schedules": schedules,
            "employees": employees
        }
    )

@app.get("/access-events-page")
def access_events_page(request: Request, db: Session = Depends(get_db)):
    events = db.query(AccessEvent).order_by(
        AccessEvent.event_time.desc()
    ).all()

    employees = db.query(Employee).order_by(Employee.full_name.asc()).all()

    return templates.TemplateResponse(
        request=request,
        name="access_events.html",
        context={
            "events": events,
            "employees": employees
        }
    )

@app.get("/run-check-lateness")
def run_check_lateness(
    work_date: date,
    db: Session = Depends(get_db)
):
    grace_period_minutes = 5

    schedules = db.query(WorkSchedule).filter(
        WorkSchedule.work_date == work_date
    ).all()

    for schedule in schedules:
        planned_start = datetime.combine(schedule.work_date, schedule.start_time)
        allowed_start = planned_start + timedelta(minutes=grace_period_minutes)

        day_start = planned_start.replace(hour=0, minute=0, second=0)
        day_end = planned_start.replace(hour=23, minute=59, second=59)

        first_entry = db.query(AccessEvent).filter(
            AccessEvent.employee_id == schedule.employee_id,
            AccessEvent.direction == "IN",
            AccessEvent.event_time >= day_start,
            AccessEvent.event_time <= day_end
        ).order_by(AccessEvent.event_time.asc()).first()

        if not first_entry:
            continue

        if first_entry.event_time > allowed_start:
            existing_violation = db.query(Violation).filter(
                Violation.employee_id == schedule.employee_id,
                Violation.schedule_id == schedule.id,
                Violation.violation_type == "Опоздание"
            ).first()

            if existing_violation:
                continue

            late_minutes = int((first_entry.event_time - allowed_start).total_seconds() // 60)

            violation = Violation(
                employee_id=schedule.employee_id,
                schedule_id=schedule.id,
                violation_type="Опоздание",
                work_date=schedule.work_date,
                planned_start_time=planned_start,
                actual_entry_time=first_entry.event_time,
                late_minutes=late_minutes,
                status="Новое",
                screenshot_path=None
            )

            db.add(violation)

    db.commit()

    return RedirectResponse(url="/dashboard", status_code=303)


@app.get("/run-check-absences")
def run_check_absences(
    work_date: date,
    db: Session = Depends(get_db)
):
    schedules = db.query(WorkSchedule).filter(
        WorkSchedule.work_date == work_date
    ).all()

    for schedule in schedules:
        planned_start = datetime.combine(schedule.work_date, schedule.start_time)

        day_start = planned_start.replace(hour=0, minute=0, second=0)
        day_end = planned_start.replace(hour=23, minute=59, second=59)

        first_entry = db.query(AccessEvent).filter(
            AccessEvent.employee_id == schedule.employee_id,
            AccessEvent.direction == "IN",
            AccessEvent.event_time >= day_start,
            AccessEvent.event_time <= day_end
        ).order_by(AccessEvent.event_time.asc()).first()

        if first_entry:
            continue

        existing_violation = db.query(Violation).filter(
            Violation.employee_id == schedule.employee_id,
            Violation.schedule_id == schedule.id,
            Violation.violation_type == "Неявка"
        ).first()

        if existing_violation:
            continue

        violation = Violation(
            employee_id=schedule.employee_id,
            schedule_id=schedule.id,
            violation_type="Неявка",
            work_date=schedule.work_date,
            planned_start_time=planned_start,
            actual_entry_time=None,
            late_minutes=None,
            status="Новое",
            screenshot_path=None
        )

        db.add(violation)

    db.commit()

    return RedirectResponse(url="/dashboard", status_code=303)

@app.post("/employees-page/create")
def create_employee_from_page(
    full_name: str = Form(...),
    department: str = Form(...),
    position: str = Form(...),
    card_id: str = Form(...),
    db: Session = Depends(get_db)
):
    existing_employee = db.query(Employee).filter(
        Employee.card_id == card_id
    ).first()

    if existing_employee:
        raise HTTPException(
            status_code=400,
            detail="Сотрудник с таким номером карты уже существует"
        )

    employee = Employee(
        full_name=full_name,
        department=department,
        position=position,
        card_id=card_id
    )

    db.add(employee)
    db.commit()

    return RedirectResponse(url="/employees-page", status_code=303)

@app.post("/schedules-page/create")
def create_schedule_from_page(
    employee_id: int = Form(...),
    work_date: date = Form(...),
    start_time: time = Form(...),
    end_time: time = Form(...),
    db: Session = Depends(get_db)
):
    employee = db.query(Employee).filter(Employee.id == employee_id).first()

    if not employee:
        raise HTTPException(
            status_code=404,
            detail="Сотрудник не найден"
        )

    schedule = WorkSchedule(
        employee_id=employee_id,
        work_date=work_date,
        start_time=start_time,
        end_time=end_time
    )

    db.add(schedule)
    db.commit()

    return RedirectResponse(url="/schedules-page", status_code=303)

@app.post("/access-events-page/create")
def create_access_event_from_page(
    employee_id: int = Form(...),
    event_time: datetime = Form(...),
    direction: str = Form(...),
    db: Session = Depends(get_db)
):
    employee = db.query(Employee).filter(Employee.id == employee_id).first()

    if not employee:
        raise HTTPException(
            status_code=404,
            detail="Сотрудник не найден"
        )

    access_event = AccessEvent(
        employee_id=employee.id,
        card_id=employee.card_id,
        event_time=event_time,
        direction=direction
    )

    db.add(access_event)
    db.commit()

    return RedirectResponse(url="/access-events-page", status_code=303)