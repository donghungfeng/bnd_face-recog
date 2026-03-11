# Sửa dòng import này (Thêm Request)
from fastapi import APIRouter, Depends, HTTPException, Request

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
from schemas import EmployeeCreate, LeaveSubmit, ExplainRequest, ReviewExplainRequest
from config import DB_PATH

router = APIRouter()

@router.get("/api/attendance")
def get_attendance(
    limit: int = 100, 
    role: Optional[str] = "user",       # Nhận role từ Client
    username: Optional[str] = None,   # Nhận username từ Client
    db: Session = Depends(get_db)
):
    # Khởi tạo câu query cơ bản
    query = db.query(Attendance, Employee).outerjoin(Employee, Attendance.username == Employee.username)
    
    # KỸ THUẬT PHÂN QUYỀN: 
    # Nếu là nhân viên bình thường (user), BẮT BUỘC chỉ được xem dữ liệu của chính mình
    if role == "user":
        if not username:
            return [] # Trả về danh sách rỗng nếu không có username
        query = query.filter(Attendance.username == username)
        
    # (Nếu là admin hoặc manager thì bỏ qua if trên, lấy toàn bộ)

    records = query.order_by(Attendance.check_in_time.desc()).limit(limit).all()
    
    result = []
    for att, emp in records:
        date_str = att.check_in_time.strftime("%Y-%m-%d") if att.check_in_time else ""
        time_str = att.check_in_time.strftime("%H:%M") if att.check_in_time else "--:--"
        display_name = emp.full_name if emp else (att.full_name or "Người lạ / Chưa ĐK")
        
        # Nội suy trạng thái
        if att.late_minutes and att.late_minutes > 0:
            status = "Đi muộn"
        else:
            status = "Đúng giờ"

        result.append({
            "id": att.id,
            "username": att.username,
            "full_name": display_name,
            "date": date_str,
            "scan_time": time_str,
            "late_minutes": att.late_minutes or 0,
            "early_minutes": att.early_minutes or 0,
            "status": status,
            "confidence": att.confidence,
            "image_path": att.image_path,
            "explanation_status": att.explanation_status,
            "explanation_reason": att.explanation_reason
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