from sqlalchemy import Column, Float, Integer, String, Date, Time, DateTime, Text, Boolean
from datetime import datetime
from database import Base
from sqlalchemy import ForeignKey
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

class ShiftAssignment(Base):
    __tablename__ = "shift_assignments"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, index=True)      # Mã nhân viên
    shift_code = Column(String, index=True)    # Mã ca trực
    shift_date = Column(Date, index=True)      # Ngày trực
    assigner = Column(String, nullable=True)

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

class LeaveRequest(Base):
    __tablename__ = "leave_requests"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, index=True)
    full_name = Column(String)
    leave_date = Column(Date, index=True)
    reason = Column(String)
    approver = Column(String, nullable=True)
    status = Column(String, default="Chờ duyệt")


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

class AppConfig(Base):
    __tablename__ = "app_configs"

    # config_key làm Khóa chính luôn (VD: "FACE_THRESHOLD", "ANTI_SPOOFING")
    config_key = Column(String(50), primary_key=True, index=True) 
    config_value = Column(String(255), nullable=False)             
    description = Column(String(255), nullable=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

