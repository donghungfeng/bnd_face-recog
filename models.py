from sqlalchemy import Column, Float, Integer, Numeric, SmallInteger, String, Date, Time, DateTime, Text, Boolean
from datetime import datetime
from database import Base
from sqlalchemy import ForeignKey, func
from sqlalchemy.orm import relationship

class Employee(Base):
    __tablename__ = "employees"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    full_name = Column(String, index=True)
    phone = Column(String, nullable=True)
    dob = Column(Date, nullable=True)
    email = Column(String, nullable=True)
    # --- THÊM 2 DÒNG NÀY (KHÓA NGOẠI) ---
    department_id = Column(Integer, ForeignKey("organization_units.id"), nullable=True)
    department = relationship("OrganizationUnit") # Tự động kết nối 2 bảng

    status = Column(String, default="active")
    notes = Column(Text, nullable=True)
    hourly_rate = Column(Integer, default=25000)
    allowance = Column(Integer, default=0)

    password = Column(String, default="123456") # Mật khẩu mặc định
    role = Column(String, default="user")       # Phân quyền: 'admin' hoặc 'user'
    is_locked = Column(Integer, default=0)      # 0: Đang hoạt động, 1: Bị khóa

    date_of_birth = Column(Date, nullable=True)
    
    # --- CÁC TRƯỜNG MỚI THÊM (v10) ---
    ccCaNhan = Column(Integer, default=1)
    ccTapTrung = Column(Integer, default=0)
    checkViTri = Column(Integer, default=1)
    checkMang = Column(Integer, default=1)
    departments = relationship("EmployeeDepartment", back_populates="employee")

class ShiftCategory(Base):
    __tablename__ = "shift_categories"
    id = Column(Integer, primary_key=True, index=True)
    shift_code = Column(String, unique=True, index=True) # VD: CA_DEM
    shift_name = Column(String)                          # VD: Ca Đêm Hồi Sức
    start_time = Column(Time)
    end_time = Column(Time)
    is_overnight = Column(Integer, default=0)            # 0: Trong ngày, 1: Qua ngày
    status = Column(String, default="active")
    notes = Column(Text, nullable=True)

    # CÁC TRƯỜNG BỔ SUNG:
    checkin_from = Column(Time, nullable=True)
    checkin_to = Column(Time, nullable=True)
    checkout_from = Column(Time, nullable=True)
    checkout_to = Column(Time, nullable=True)
    work_hours = Column(Float, nullable=True)
    work_days = Column(Float, nullable=True)
    day_coefficient = Column(Float, nullable=True)

class ShiftAssignment(Base):
    __tablename__ = "shift_assignments"
    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False)
    shift_code = Column(String, index=True)    # Mã ca trực
    shift_date = Column(Date, index=True)      # Ngày trực

class Attendance(Base):
    __tablename__ = "attendance"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, index=True)
    full_name = Column(String)
    check_in_time = Column(DateTime, default=datetime.now)
    image_path = Column(String, nullable=True) 
    late_minutes = Column(Integer, default=0)
    early_minutes = Column(Integer, default=0)
    explanation_status = Column(String, default="")
    explanation_reason = Column(Text, nullable=True)

    confidence = Column(Float, nullable=True)
    is_fraud = Column(Boolean, default=False)
    fraud_note = Column(String(255), nullable=True)

    client_ip = Column(String(50), nullable=True)  
    latitude = Column(Float, nullable=True)        
    longitude = Column(Float, nullable=True)       
    attendance_type = Column(String(50), default="Tập trung")
    note = Column(Text, nullable=True)


class OrganizationUnit(Base):
    __tablename__ = "organization_units"
    id = Column(Integer, primary_key=True, index=True)
    unit_code = Column(String, unique=True, index=True) # Mã đơn vị (VD: K_CAPCUU)
    unit_name = Column(String)                          # Tên đơn vị (VD: Khoa Cấp Cứu)
    unit_type = Column(String)                          # Loại: Khối, Trung tâm, Khoa, Phòng...
    parent_id = Column(Integer, ForeignKey("organization_units.id"), nullable=True) # Đơn vị cha
    order_num = Column(Integer, default=1)              # Số thứ tự hiển thị
    level = Column(Integer, default=1)                  # Cấp phân cấp (1, 2, 3...)
    location = Column(String, nullable=True)            # Vị trí (Tầng 1 - Tòa A...)
    status = Column(String, default="active")           # Trạng thái
    notes = Column(Text, nullable=True)                 # Ghi chú

    # Relationship để truy vấn con/cha dễ dàng nếu cần
    children = relationship("OrganizationUnit", backref="parent", remote_side=[id])

class MonthlyRecord(Base):
    __tablename__ = "monthly_records"
    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False)
    shift_code = Column(String(50), nullable=True)
    date = Column(Date, index=True)
    checkin_time = Column(Time, nullable=True)
    checkout_time = Column(Time, nullable=True)
    late_minutes = Column(Integer, default=0)
    early_minutes = Column(Integer, default=0)
    status = Column(Integer, default=0)
    explanation_reason = Column(Text, nullable=True)
    explanation_status = Column(Integer, default=0)
    checkin_image_path = Column(String, nullable=True)
    checkout_image_path = Column(String, nullable=True)
    actual_hours = Column(Float, default=0)
    actual_workday = Column(Float, default=0)
    note = Column(Text, nullable=True)

class AppConfig(Base):
    __tablename__ = "app_configs"

    # config_key làm Khóa chính luôn (VD: "FACE_THRESHOLD", "ANTI_SPOOFING")
    config_key = Column(String(50), primary_key=True, index=True) 
    config_value = Column(String(255), nullable=False)             
    description = Column(String(255), nullable=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

class Explanation(Base):
    __tablename__ = "explanation"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(255), index=True, nullable=False)
    date = Column(Date, server_default=func.current_date()) 
    reason = Column(Text, nullable=False)
    status = Column(String(50), nullable=False)
    shift_code = Column(String(255), nullable=True) # Mã ca trực (VD: CA_DEM)
    attached_file = Column(String(1024), nullable=True)
    
class Wifi(Base):
    __tablename__ = "wifi"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    password = Column(String(255), nullable=False)
    location = Column(String(255), nullable=True)
    ip_address = Column(String(45), nullable=True)
    note = Column(Text, nullable=True)
    status = Column(String(50), nullable=False, default="active")


class Holiday(Base):
    __tablename__ = "holidays"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(50), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    from_date = Column(Date, nullable=False)
    to_date = Column(Date, nullable=False)
    num_days = Column(Numeric(4, 1), nullable=False)         # Decimal(4,1)
    scope = Column(Text, nullable=True)                      # Áp dụng cho đối tượng nào
    status = Column(SmallInteger, server_default='1')        # TinyInt mặc định là 1 (Active)


# ==========================================
# 2. BẢNG LOẠI NGHỈ PHÉP (leave_types)
# ==========================================
class LeaveType(Base):
    __tablename__ = "leave_types"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(50), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    benefit_rate = Column(Numeric(5, 2), server_default='100.00') # Decimal(5,2) mặc định 100.00%
    max_num_days = Column(Integer, server_default='0')
    scope = Column(Text, nullable=True)
    status = Column(SmallInteger, server_default='1')
    note = Column(Text, nullable=True)

    # Mối quan hệ 1-Nhiều với bảng leave_requests (1 Loại phép có nhiều Đơn xin nghỉ)
    requests = relationship("LeaveRequest", back_populates="leave_type")


# ==========================================
# 3. BẢNG ĐƠN XIN NGHỈ PHÉP (leave_requests)
# ==========================================
class LeaveRequest(Base):
    __tablename__ = "leave_requests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(255), nullable=False, index=True)
    fullname = Column(String(255), nullable=True)             # BỔ SUNG: Tên người xin nghỉ
    from_date = Column(Date, nullable=False)
    from_session = Column(String(50), default="Cả ngày")      # BỔ SUNG: Sáng / Chiều / Cả ngày
    to_date = Column(Date, nullable=False)
    to_session = Column(String(50), default="Cả ngày")        # BỔ SUNG: Sáng / Chiều / Cả ngày
    type_id = Column(Integer, ForeignKey("leave_types.id"), nullable=False)
    reason = Column(Text, nullable=True)
    approver_username = Column(String(255), nullable=True)
    approver_fullname = Column(String(255), nullable=True)
    status = Column(String(50), server_default='PENDING')

    leave_type = relationship("LeaveType", back_populates="requests")
    attached_image = Column(String(255), nullable=True)

class EmployeeDepartment(Base):
    __tablename__ = "employee_departments"
    
    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False)
    department_id = Column(Integer, ForeignKey("organization_units.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(256), nullable=True)
    is_primary = Column(SmallInteger, default=1) # 1: Chính, 0: Phụ
    status = Column(String(50), default="active")
    assigned_at = Column(DateTime, default=datetime.now)

    # Relationship để join ngược lại lấy tên phòng ban
    department = relationship("OrganizationUnit")
    employee = relationship("Employee", back_populates="departments")

class ShiftSwapRequest(Base):
    __tablename__ = "shift_swap_request"

    id = Column(Integer, primary_key=True, index=True)
    employee_source_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    employee_target_id = Column(Integer, ForeignKey("employees.id"), nullable=True) 
    source_date = Column(Date, nullable=False)
    target_date = Column(Date, nullable=False)
    source_shift_code = Column(String(50), nullable=False)
    target_shift_code = Column(String(50), nullable=False)
    reason = Column(Text, nullable=True)
    status = Column(String(20), default="PENDING") 
    approved_by_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    attached_file = Column(String(1024), nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    is_all_day = Column(Integer, default=0)

    # Relationships giúp lấy thông tin nhân viên dễ dàng hơn
    source_employee = relationship("Employee", foreign_keys=[employee_source_id])
    target_employee = relationship("Employee", foreign_keys=[employee_target_id])
    approver = relationship("Employee", foreign_keys=[approved_by_id])
