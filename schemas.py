from pydantic import BaseModel, ConfigDict
from typing import List, Optional
from datetime import date, time, datetime

class DepartmentAssignment(BaseModel):
    department_id: int
    role: str = "user"
    is_primary: int = 0

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
    status: Optional[str] = "active"
    notes: Optional[str] = None
    hourly_rate: int = 25000
    allowance: int = 0
    # CÁC TRƯỜNG MỚI:
    password: Optional[str] = "123456"
    is_locked: Optional[int] = 0
    date_of_birth: Optional[date] = None

    ccCaNhan: Optional[int] = None
    ccTapTrung: Optional[int] = None
    checkViTri: Optional[int] = None
    checkMang: Optional[int] = None
    departments: Optional[List[DepartmentAssignment]] = None
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
    checkin_image_path: Optional[str] = None
    checkout_image_path: Optional[str] = None
    actual_hours: float = 0
    actual_workday: float = 0
    note: Optional[str] = None

class MonthlyRecordOut(MonthlyRecordBase):
    id: Optional[int] = None
    full_name: Optional[str] = None
    username: Optional[str] = None
    shift_display_name: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)

class AttendanceSchema(BaseModel):
    id: int
    username: str
    full_name: str
    check_in_time: datetime
    image_path: Optional[str] = None
    late_minutes: Optional[int] = 0      # Nếu null thì mặc định là 0 phút
    early_minutes: Optional[int] = 0     # Nếu null thì mặc định là 0 phút
    explanation_status: Optional[str] = None # Nếu null thì mặc định là None
    explanation_reason: Optional[str] = None

    confidence: Optional[float] = None
    is_fraud: bool = False
    fraud_note: Optional[str] = None

    client_ip: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    attendance_type: str = "Tập trung"
    note: Optional[str] = None
    class Config:
        orm_mode = True
    
class AttendanceSummary(BaseModel):
    employee_id: int
    username: str
    target_date: date
    # Danh sách các lần quét thực tế (đối tượng Model Attendance)
    scans: list[AttendanceSchema]

    model_config = ConfigDict(
        from_attributes=True,
        arbitrary_types_allowed=True
    )

    class Config:
        arbitrary_types_allowed = True
        orm_mode = True
    
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

class UpdateImageUrlRequest(BaseModel):
    filename: str
    image_url: str

class UpdateExplanationRequest(BaseModel):
    id: int
    explanation_reason: str
    explanation_status: int

# Thêm các class này vào cuối file schemas.py

class ExplanationCreate(BaseModel):
    username: str
    reason: str
    status: str
    date: date
    shift_code: str
    attached_file: Optional[str] = None  # <-- THÊM MỚI

class ExplanationResponse(BaseModel):
    id: int
    username: str
    date: date
    reason: str
    status: str
    shift_name: Optional[str] = None
    shift_code: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)
    attached_file: Optional[str] = None  # <-- THÊM MỚI

    class Config:
        arbitrary_types_allowed = True
        orm_mode = True

class PaginatedExplanationResponse(BaseModel):
    total: int
    items: list[ExplanationResponse]
    skip: int
    limit: int
    shift_code: Optional[str] = None
    

class ExplanationUpdate(BaseModel):
    date: date
    reason: str
    shift_code: Optional[str] = None
    attached_file: Optional[str] = None  # <-- THÊM MỚI

class ChangeMyPassword(BaseModel):
    old_password: str
    new_password: str

class UpdateMyProfile(BaseModel):
    full_name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    dob: Optional[date] = None
    date_of_birth: Optional[date] = None
    notes: Optional[str] = None
    ccCaNhan: Optional[int] = None
    ccTapTrung: Optional[int] = None
    
class WifiBase(BaseModel):
    name: str
    password: str
    location: Optional[str] = None
    ip_address: Optional[str] = None
    note: Optional[str] = None
    status: str = "active"
    
# Bổ sung vào cuối schemas.py
class WifiCreate(WifiBase):
    pass

class WifiUpdate(BaseModel):
    name: Optional[str] = None
    password: Optional[str] = None
    location: Optional[str] = None
    ip_address: Optional[str] = None
    note: Optional[str] = None
    status: Optional[str] = None

class WifiResponse(WifiBase):
    id: int
    model_config = ConfigDict(from_attributes=True)
    class Config:
        arbitrary_types_allowed = True
        orm_mode = True
    

class ScanFraudRequest(BaseModel):
    start_date: str # Định dạng YYYY-MM-DD
    end_date: str

class EmployeeDepartmentBase(BaseModel):
    employee_id: int
    department_id: int
    role: Optional[str] = None
    is_primary: int = 1
    status: str = "active"

class EmployeeDepartmentCreate(EmployeeDepartmentBase):
    employee_id: int
    is_primary: Optional[int] = None
    status: Optional[str] = None
    department_id: int
    role: Optional[str] = None

class EmployeeDepartmentUpdate(BaseModel):
    id: int
    employee_id: int
    role: Optional[str] = None
    is_primary: Optional[int] = None
    status: Optional[str] = None
    department_id: Optional[str] = None

class EmployeeDepartmentOut(EmployeeDepartmentBase):
    id: int
    employee_id: int
    department_id: int
    role: Optional[str] = None
    is_primary: int = 1
    is_all_day: int = 0
    status: str = "active"
    assigned_at: datetime
    # Thêm thông tin tên phòng ban để hiển thị ở Frontend
    unit_name: Optional[str] = None 
    unit_code: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

# 1. Base Schema chứa toàn bộ các trường dùng chung cho cả Create, Update và Get
class ShiftSwapBase(BaseModel):
    employee_source_id: int
    employee_target_id: Optional[int] = None
    source_date: date
    target_date: date
    source_shift_code: str
    target_shift_code: str
    reason: Optional[str] = None
    status: Optional[str] = "PENDING"
    approved_by_id: Optional[int] = None
    attached_file: Optional[str] = None

# 2. Schema cho CREATE (Không có ID, kế thừa nguyên si từ Base)
class ShiftSwapCreate(ShiftSwapBase):
    pass

# 3. Schema cho UPDATE (Kế thừa từ Base nhưng BẮT BUỘC phải truyền lên ID)
class ShiftSwapUpdate(ShiftSwapBase):
    id: int

# 4. Schema cho GET response trả về (Có ID và thêm thời gian tạo/cập nhật)
class ShiftSwapOut(ShiftSwapBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    # Nếu bạn muốn trả về thêm tên nhân viên thì có thể thêm các trường này:
    # source_employee_name: Optional[str] = None
    # target_employee_name: Optional[str] = None

    # model_config = ConfigDict(from_attributes=True)
    class Config:
        orm_mode = True

class PaginatedShiftSwapResponse(BaseModel):
    total: int
    items: list[ShiftSwapOut]
    skip: int
    limit: int