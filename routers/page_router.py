from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/verify")
def read_verify(): return FileResponse("verify.html")

@router.get("/enroll")
def read_enroll(): return FileResponse("enroll.html")

@router.get("/")
@router.get("/dashboard")
def read_dashboard(request: Request): return templates.TemplateResponse("dashboard.html", {"request": request})

@router.get("/employees")
def read_employees(request: Request): return templates.TemplateResponse("employees.html", {"request": request})

@router.get("/shifts")
def read_shifts(request: Request): return templates.TemplateResponse("shifts.html", {"request": request})

@router.get("/attendance")
def read_attendance(request: Request): return templates.TemplateResponse("attendance.html", {"request": request})

@router.get("/calendar")
def read_calendar(request: Request): return templates.TemplateResponse("calendar.html", {"request": request})

@router.get("/payroll")
def read_payroll(request: Request): return templates.TemplateResponse("payroll.html", {"request": request})

@router.get("/login")
def read_login(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@router.get("/faces")
def read_faces(request: Request): 
    return templates.TemplateResponse("faces.html", {"request": request})