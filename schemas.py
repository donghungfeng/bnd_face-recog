from pydantic import BaseModel
from typing import Optional
from datetime import date, time

class FaceRequest(BaseModel):
    user_id: str = None
    image_base64: str
    full_image_base64: str = None

class UnregisterRequest(BaseModel):
    user_id: str

class ExplainRequest(BaseModel):
    id: int
    reason: str

class EmployeeCreate(BaseModel):
    username: str
    full_name: str
    phone: Optional[str] = None
    dob: Optional[date] = None
    email: Optional[str] = None
    department_id: Optional[int] = None
    status: Optional[str] = "active"
    notes: Optional[str] = None
    hourly_rate: int = 25000
    allowance: int = 0
    # CÁC TRƯỜNG MỚI:
    password: Optional[str] = "123456"
    role: Optional[str] = "user"
    is_locked: Optional[int] = 0
    date_of_birth: Optional[date] = None

# Thêm schema này dùng cho API đổi mật khẩu
class PasswordUpdate(BaseModel):
    new_password: str   

class ShiftCategoryCreate(BaseModel):
    shift_code: str
    shift_name: str
    start_time: time
    end_time: time
    is_overnight: int = 0
    status: str = "active"
    notes: Optional[str] = None

class ShiftAssignmentCreate(BaseModel):
    username: str
    shift_code: str
    shift_date: date
    assigner: Optional[str] = None

class LeaveSubmit(BaseModel):
    username: str
    leave_date: date
    reason: str
    approver: str = ""

class OrgUnitCreate(BaseModel):
    unit_code: str
    unit_name: str
    unit_type: str
    parent_id: Optional[int] = None
    order_num: int = 1
    level: int = 1
    location: Optional[str] = None
    status: str = "active"
    notes: Optional[str] = None


class ReviewExplainRequest(BaseModel):
    id: int
    status: str
    role: str = "admin"

class SingleFaceDeleteRequest(BaseModel):
    filename: str
