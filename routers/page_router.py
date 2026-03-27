from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/verify")
def read_verify(): return FileResponse("verify.html")

@router.get("/verify_new")
def read_verify(): return FileResponse("verify_new.html")

@router.get("/verify_v3")
def read_verify(): return FileResponse("verify_v3.html")

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

@router.get("/explanation")
def read_explanation(request: Request): return templates.TemplateResponse("explanation.html", {"request": request})

@router.get("/user_info")
def read_employees_info(request: Request): return templates.TemplateResponse("employees_info.html", {"request": request})

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

@router.get("/admin_logs")
def read_admin_logs(request: Request):
    return templates.TemplateResponse("admin_logs.html", {"request": request})

@router.get("/configs")
async def configs_page(request: Request):
    return templates.TemplateResponse("configs.html", {"request": request})

@router.get("/enroll_personal")
async def enroll_personal_page(request: Request):
    return templates.TemplateResponse("enroll_personal.html", {"request": request})

@router.get("/verify_personal")
async def verify_personal_page(request: Request):
    return templates.TemplateResponse("verify_personal.html", {"request": request})

@router.get("/verify_personal_fix")
async def verify_personal_page(request: Request):
    return templates.TemplateResponse("verify_personal_fix.html", {"request": request})


@router.get("/test_ai")
async def test_ai_page(request: Request):
    return templates.TemplateResponse("test_ai.html", {"request": request})

@router.get("/enroll_image")
async def enroll_image(request: Request):
    return templates.TemplateResponse("enroll_image.html", {"request": request})

@router.get("/wifi")
async def wifi(request: Request):
    return templates.TemplateResponse("wifi.html", {"request": request})