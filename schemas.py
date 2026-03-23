from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import date, time

import models

class FaceRequest(BaseModel):
    user_id: str = None
    image_base64: str
    full_image_base64: str = None
    client_public_ip: str = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    attendance_type: str = "Cá nhân"

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
    
    # CÁC TRƯỜNG MỚI THÊM:
    checkin_from: Optional[time] = None
    checkin_to: Optional[time] = None
    checkout_from: Optional[time] = None
    checkout_to: Optional[time] = None
    work_hours: Optional[float] = None
    work_days: Optional[float] = None
    day_coefficient: Optional[float] = None

class ShiftAssignmentCreate(BaseModel):
    employee_id: int
    shift_code: str
    shift_date: date

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

class ConfigUpsertRequest(BaseModel):
    config_key: str
    config_value: str
    description: Optional[str] = None


class CheckIPRequest(BaseModel):
    user_id: str
    client_public_ip: str

class PersonalEnrollRequest(BaseModel):
    user_id: str
    image_base64: str
    client_public_ip: str 

class PersonalVerifyRequest(BaseModel):
    user_id: str
    image_base64: str
    client_public_ip: str
    full_image_base64: Optional[str] = None

    latitude: Optional[float] = None
    longitude: Optional[float] = None
    attendance_type: str = "Cá nhân"
    note: Optional[str] = ""

class MarkFraudRequest(BaseModel):
    id: int
    is_fraud: bool
    fraud_note: str = ""
    role: str = ""

class TestFaceRequest(BaseModel):
    image_base64: str
    
class AttendanceUpdateRequest(BaseModel):
    scan_time: str = None  # Nhận giờ mới (vd: 07:45:00)
    note: str = None       # Nhận ghi chú mới
    role: str = None

class MonthlyRecordBase(BaseModel):
    employee_id: int
    shift_code: Optional[str] = None
    date: date
    checkin_time: Optional[time] = None
    checkout_time: Optional[time] = None
    late_minutes: int = 0
    early_minutes: int = 0
    status: int = 0
    explanation_reason: Optional[str] = None
    explanation_status: int = 0
    note: Optional[str] = None

class MonthlyRecordOut(MonthlyRecordBase):
    id: Optional[int] = None
    full_name: Optional[str] = None
    username: Optional[str] = None
    shift_display_name: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)
    
class AttendanceSummary(BaseModel):
    employee_id: int
    username: str
    target_date: date
    # Danh sách các lần quét thực tế (đối tượng Model Attendance)
    scans: list[models.Attendance]

    model_config = ConfigDict(
        from_attributes=True,
        arbitrary_types_allowed=True
    )
    
class AttendanceSummaryByEmployee(BaseModel):
    # Thông tin cá nhân
    employee_id: int
    username: str
    full_name: str
    department: Optional[str] = None
    position: Optional[str] = None

    # Tổng số bản ghi trong kỳ
    total_days: int

    # Số lượng theo từng trạng thái
    present_count:            int = 0  # PRESENT = 1
    late_count:               int = 0  # LATE = 2
    early_leave_count:        int = 0  # EARLY_LEAVE = 3
    on_leave_count:           int = 0  # ON_LEAVE = 4
    unpaid_leave_count:       int = 0  # UNPAID_LEAVE = 5
    late_and_early_count:     int = 0  # LATE_AND_EARLY_LEAVE = 6
    in_progress_count:        int = 0  # IN_PROGRESS = 7
    absent_count:             int = 0  # ABSENT = 0

    # Phút tổng cộng
    total_late_minutes:  int = 0
    total_early_minutes: int = 0

    class Config:
        from_attributes = True
