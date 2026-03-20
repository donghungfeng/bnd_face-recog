# Sửa dòng import này (Thêm Request)
from fastapi import APIRouter, Depends, HTTPException, Request, Query

# Thêm 2 dòng này để hỗ trợ trả về giao diện HTML (nếu bạn để các hàm render HTML ở file này)
from fastapi.templating import Jinja2Templates
templates = Jinja2Templates(directory="templates")

from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from datetime import datetime, date, time
from collections import defaultdict
import openpyxl, io
from openpyxl.styles import Font, PatternFill, Alignment
import os
from typing import Optional

from database import get_db
from models import Employee, Attendance, LeaveRequest, ShiftCategory
from schemas import EmployeeCreate, LeaveSubmit, ExplainRequest, ReviewExplainRequest, MarkFraudRequest
from config import DB_PATH

router = APIRouter()

from routers.auth_router import get_current_user

@router.get("/api/attendance")
def get_attendance(
    limit: int = 50, 
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    username: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    role = current_user.get("role", "user")
    current_username = current_user.get("username")
    
    from sqlalchemy import func
    
    # 1. Khởi tạo điều kiện lọc theo phân quyền
    filter_conditions = []

    if role == "user":
        filter_conditions.append(Attendance.username == current_username)
    elif role == "manager":
        manager_emp = db.query(Employee).filter(Employee.username == current_username).first()
        if not manager_emp or manager_emp.department_id is None:
            return []
        dept_users = [u[0] for u in db.query(Employee.username).filter(Employee.department_id == manager_emp.department_id).all()]
        
        if username:
            if username in dept_users:
                filter_conditions.append(Attendance.username == username)
            else:
                return []
        else:
            filter_conditions.append(Attendance.username.in_(dept_users))
    elif role == "admin":
        if username:
            filter_conditions.append(Attendance.username == username)

    # 1.1 Lọc thời gian
    if start_date:
        filter_conditions.append(func.date(Attendance.check_in_time) >= start_date)
    if end_date:
        filter_conditions.append(func.date(Attendance.check_in_time) <= end_date)
        
    # 2. Query trực tiếp từ bảng Attendance (Không cần nhóm theo ngày nữa để xem được mọi lần quét)
    # Nếu bạn vẫn muốn chỉ hiện "Vào - Ra" gộp thì dùng logic dưới, 
    # nhưng thường trang Logs Admin nên hiện từng bản ghi một để kiểm soát.
    
    query_logs = db.query(Attendance, Employee.full_name).\
        join(Employee, Attendance.username == Employee.username, isouter=True).\
        filter(*filter_conditions).\
        order_by(Attendance.check_in_time.desc()).\
        limit(limit).all()
    
    result = []
    for log, full_name in query_logs:
        result.append({
            "id": log.id,
            "username": log.username,
            "full_name": full_name or log.full_name or "Chưa danh tính",
            "date": log.check_in_time.strftime("%Y-%m-%d"),
            "scan_time": log.check_in_time.strftime("%H:%M:%S"),
            "confidence": log.confidence,
            "image_path": log.image_path,
            "is_fraud": bool(log.is_fraud), 
            "fraud_note": log.fraud_note or "",
            "client_ip": log.client_ip or "",
            "latitude": log.latitude,
            "longitude": log.longitude,
            "attendance_type": log.attendance_type,
            "explanation_status": log.explanation_status,
            "explanation_reason": log.explanation_reason,
            "note": log.note or ""
        })
        
    return result

@router.post("/api/attendance/explain")
def submit_explanation(req: ExplainRequest, db: Session = Depends(get_db)):
    record = db.query(Attendance).filter(Attendance.id == req.id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Không tìm thấy bản ghi")
    
    record.explanation_reason = req.reason
    record.explanation_status = "Đã gửi" # Đổi trạng thái
    db.commit()
    return {"status": "success", "message": "Đã gửi giải trình thành công"}


# --- (Thêm vào phần 6. API DATABASE) ---
@router.get("/api/attendance/calendar")
def get_calendar_data(username: str, month: int, year: int, db: Session = Depends(get_db)):
    start_date = datetime(year, month, 1)
    if month == 12:
        end_date = datetime(year + 1, 1, 1)
    else:
        end_date = datetime(year, month + 1, 1)

    # 1. Lấy dữ liệu chấm công
    records = db.query(Attendance).filter(
        Attendance.username == username,
        Attendance.check_in_time >= start_date,
        Attendance.check_in_time < end_date
    ).all()

    # 2. Lấy dữ liệu xin nghỉ phép/công tác
    leaves = db.query(LeaveRequest).filter(
        LeaveRequest.username == username,
        LeaveRequest.leave_date >= start_date.date(),
        LeaveRequest.leave_date < end_date.date()
    ).all()

    daily_data = defaultdict(lambda: {"in": None, "out": None, "work_time": None, "leave": None})

    # Đưa dữ liệu nghỉ phép vào ngày tương ứng
    for l in leaves:
        daily_data[l.leave_date.day]["leave"] = {
            "reason": l.reason,
            "status": l.status,
            "approver": l.approver
        }

    # Đưa dữ liệu Giờ Vào/Ra vào ngày
    for r in records:
        day = r.check_in_time.day
        t = r.check_in_time.time()
        time_str = t.strftime("%H:%M")

        if t.hour < 12:
            if not daily_data[day]["in"] or time_str < daily_data[day]["in"]:
                daily_data[day]["in"] = time_str
        else:
            if not daily_data[day]["out"] or time_str > daily_data[day]["out"]:
                daily_data[day]["out"] = time_str

    # 3. Tính toán CÔNG THỰC TẾ = Ra - Vào - 1 tiếng (nghỉ trưa)
    for day, data in daily_data.items():
        if data["in"] and data["out"]:
            t_in = datetime.strptime(data["in"], "%H:%M")
            t_out = datetime.strptime(data["out"], "%H:%M")
            diff_seconds = (t_out - t_in).total_seconds()
            
            work_seconds = diff_seconds - 3600 # Trừ đi 3600 giây (1 tiếng nghỉ trưa)
            
            if work_seconds > 0:
                h = int(work_seconds // 3600)
                m = int((work_seconds % 3600) // 60)
                data["work_time"] = f"{h}h{m}p"
            else:
                data["work_time"] = "0h"

    return daily_data

@router.put("/api/attendance/review_explain")
def review_explanation(req: ReviewExplainRequest, db: Session = Depends(get_db)):
    # Bước 1: Kiểm tra quyền truy cập (RBAC - Role Based Access Control)
    if req.role not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="Truy cập bị từ chối: Chỉ Quản lý hoặc Admin mới được phép duyệt!")

    # Bước 2: Tìm bản ghi chấm công tương ứng
    record = db.query(Attendance).filter(Attendance.id == req.id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Không tìm thấy bản ghi chấm công này!")

    # Bước 3: Kiểm tra tính hợp lệ của trạng thái
    if req.status not in ["Đã duyệt", "Từ chối"]:
        raise HTTPException(status_code=400, detail="Trạng thái phê duyệt không hợp lệ!")

    # Bước 4: Cập nhật dữ liệu vào DB
    record.explanation_status = req.status
    
    # Mẹo: Nếu bảng Attendance của bạn có cột 'approver_name', bạn có thể lưu luôn ai là người duyệt ở đây
    # record.approver_name = "Tên Admin đang đăng nhập"
    
    db.commit()
    
    return {
        "status": "success", 
        "message": f"Đã {req.status.lower()} giải trình thành công!"
    }

@router.put("/api/attendance/mark_fraud")
def mark_fraud(req: MarkFraudRequest, db: Session = Depends(get_db)):
    # Chỉ Admin hoặc Manager mới được phép đánh dấu gian lận
    if req.role not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="Không có quyền thực hiện")
        
    # Tìm bản ghi chấm công
    record = db.query(Attendance).filter(Attendance.id == req.id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Không tìm thấy bản ghi")
        
    # Cập nhật trạng thái
    record.is_fraud = req.is_fraud
    record.fraud_note = req.fraud_note if req.is_fraud else ""
    
    db.commit()
    return {"status": "success", "message": "Đã cập nhật trạng thái gian lận"}


@router.delete("/api/attendance/{record_id}")
def delete_attendance_record(
    record_id: int, 
    role: str = Query(..., description="Quyền của người đang thao tác"), 
    db: Session = Depends(get_db)
):
    # 1. Chặn cửa: Chỉ Admin/Manager mới được phép gọi lệnh Delete
    if role not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="Truy cập bị từ chối: Chỉ Quản lý hoặc Admin mới được phép xóa!")

    # 2. Tìm bản ghi trong Database
    record = db.query(Attendance).filter(Attendance.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Không tìm thấy bản ghi này trong cơ sở dữ liệu.")

    # 3. Trảm file ảnh vật lý dưới ổ cứng (Nếu có)
    if record.image_path:
        physical_img_path = "." + record.image_path
        try:
            if os.path.exists(physical_img_path):
                os.remove(physical_img_path)
                print(f"✅ Đã dọn rác ổ cứng: Xóa file {physical_img_path}")
        except Exception as e:
            print(f"⚠️ Không thể xóa file ảnh vật lý (có thể file đã mất): {e}")

    # 4. Trảm dữ liệu trong Database
    try:
        db.delete(record)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Lỗi SQL khi xóa bản ghi.")

    return {"status": "success", "message": f"Đã xóa vĩnh viễn bản ghi ID {record_id}"}