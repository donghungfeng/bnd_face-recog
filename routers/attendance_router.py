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
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    role = current_user.get("role", "user")
    username = current_user.get("username")
    from sqlalchemy import func
    from datetime import timedelta
    from models import ShiftAssignment, ShiftCategory
    
    # 1. Khởi tạo điều kiện lọc theo phân quyền
    filter_conditions = []
    if role == "user":
        if not username:
            return [] # Trả về rỗng nếu không có định danh
        filter_conditions.append(Attendance.username == username)
    elif role == "manager":
        if not username:
            return []
        # Tìm Manager để lấy department_id
        manager_emp = db.query(Employee).filter(Employee.username == username).first()
        if manager_emp and manager_emp.department_id is not None:
            # Lấy danh sách nhân viên trong cùng phòng ban
            dept_users_query = db.query(Employee.username).filter(Employee.department_id == manager_emp.department_id).all()
            dept_users = [u[0] for u in dept_users_query]
            if dept_users:
                filter_conditions.append(Attendance.username.in_(dept_users))
            else:
                return [] # Phòng ban không có ai
        else:
            return [] # Manager chưa được gán phòng ban thì không xem được gì
            
    # 1.1 Lọc theo mốc thời gian (Date Filter)
    if start_date:
        filter_conditions.append(func.date(Attendance.check_in_time) >= start_date)
    if end_date:
        filter_conditions.append(func.date(Attendance.check_in_time) <= end_date)
        
    # 2. Nhóm các bản ghi theo (username, ngày)
    distinct_pairs = db.query(
        Attendance.username,
        func.date(Attendance.check_in_time).label('d_date_str')
    ).filter(*filter_conditions).group_by(
        Attendance.username, func.date(Attendance.check_in_time)
    ).order_by(
        func.date(Attendance.check_in_time).desc()
    ).limit(limit).all()
    
    result = []
    for uname, d_date_str in distinct_pairs:
        if not d_date_str:
            continue
            
        d_date = datetime.strptime(d_date_str, "%Y-%m-%d").date()
        
        # 3. Lấy tất cả các lần quét trong ngày của user này (Sắp xếp từ cũ đến mới)
        day_logs = db.query(Attendance).filter(
            Attendance.username == uname,
            func.date(Attendance.check_in_time) == d_date_str
        ).order_by(Attendance.check_in_time.asc()).all()
        
        if not day_logs:
            continue
            
        first_log = day_logs[0] # Lần check-in đầu tiên trong ngày
        last_log = day_logs[-1] # Lần check-out cuối cùng trong ngày
        
        emp = db.query(Employee).filter(Employee.username == uname).first()
        display_name = emp.full_name if emp else (first_log.full_name or "Người lạ / Chưa ĐK")
        
        date_str = d_date_str
        first_time_str = first_log.check_in_time.strftime("%H:%M:%S") if first_log.check_in_time else "--:--"
        last_time_str = last_log.check_in_time.strftime("%H:%M:%S") if last_log.check_in_time else "--:--"
        
        # Gộp giờ hiển thị: "Giờ_Vào - Giờ_Ra"
        if first_log.id == last_log.id:
            time_str = first_time_str
        else:
            time_str = f"{first_time_str} - {last_time_str}"
            
        calculated_late_minutes = 0
        calculated_early_minutes = 0
        is_shift_assigned = False
        shift_display_code = "X"
        
        if emp:
            shift_assignment = db.query(ShiftAssignment).filter(
                ShiftAssignment.employee_id == emp.id,
                ShiftAssignment.shift_date == d_date
            ).first()
            
            if shift_assignment:
                is_shift_assigned = True
                shift_code = shift_assignment.shift_code
            else:
                is_shift_assigned = False
                shift_code = 'X'
                
                # NẾU LÀ CA X, CHECK XEM HÔM QUA CÓ PHẢI CA T HOẶC K KHÔNG
                # Nếu hôm qua là ca T/K thì ngày hôm nay thực chất là ngày nghỉ bù/check-out của ca trước
                prev_date = d_date - timedelta(days=1)
                prev_shift = db.query(ShiftAssignment).filter(
                    ShiftAssignment.employee_id == emp.id,
                    ShiftAssignment.shift_date == prev_date
                ).first()
                if prev_shift and prev_shift.shift_code in ['T', 'K']:
                    continue # Bỏ qua hoàn toàn, không hiển thị thành dòng "Chưa phân ca" nữa
                
            shift_display_code = shift_code
            shift_cat = db.query(ShiftCategory).filter(ShiftCategory.shift_code == shift_code).first()
            
            if shift_cat:
                if shift_code in ['T', 'K']:
                    # TRƯỜNG HỢP CA "T", "K" (Làm qua đêm / Sang ngày hôm sau)
                    checkin_to = shift_cat.checkin_to
                    if checkin_to and first_log.check_in_time:
                        checkin_to_dt = datetime.combine(d_date, checkin_to)
                        if shift_cat.checkin_from:
                            checkin_from_dt = datetime.combine(d_date, shift_cat.checkin_from)
                            if first_log.check_in_time < checkin_from_dt or first_log.check_in_time > checkin_to_dt:
                                if first_log.check_in_time > checkin_to_dt:
                                    calculated_late_minutes = int((first_log.check_in_time - checkin_to_dt).total_seconds() / 60)
                        else:
                            if first_log.check_in_time > checkin_to_dt:
                                calculated_late_minutes = int((first_log.check_in_time - checkin_to_dt).total_seconds() / 60)
                                
                    # Tính về sớm và cập nhật hiển thị giờ ra: Xem ngày mai (D+1)
                    next_date = d_date + timedelta(days=1)
                    next_date_str = next_date.strftime("%Y-%m-%d")
                    next_day_logs = db.query(Attendance).filter(
                        Attendance.username == uname,
                        func.date(Attendance.check_in_time) == next_date_str
                    ).order_by(Attendance.check_in_time.desc()).all()
                    
                    if not next_day_logs:
                        calculated_early_minutes = "Waiting"
                    else:
                        latest_next_day = next_day_logs[0] # Muộn nhất của ngày hôm sau
                        # Cập nhật giờ hiển thị Check-out thành giờ của ngày hôm sau
                        time_str = f"{first_time_str} - {latest_next_day.check_in_time.strftime('%H:%M:%S')} (hsau)"
                        
                        checkout_to = shift_cat.checkout_to
                        if checkout_to and latest_next_day.check_in_time:
                            checkout_to_dt = datetime.combine(next_date, checkout_to)
                            if latest_next_day.check_in_time < checkout_to_dt:
                                calculated_early_minutes = int((checkout_to_dt - latest_next_day.check_in_time).total_seconds() / 60)
                else:
                    # CA KHÁC (Ca thường)
                    std_in = shift_cat.checkin_to or shift_cat.start_time
                    std_out = shift_cat.checkout_from or shift_cat.end_time
                    
                    if std_in and first_log.check_in_time:
                        std_in_dt = datetime.combine(d_date, std_in)
                        if first_log.check_in_time > std_in_dt:
                            calculated_late_minutes = int((first_log.check_in_time - std_in_dt).total_seconds() / 60)
                            
                    if std_out and last_log.check_in_time:
                        std_out_dt = datetime.combine(d_date, std_out)
                        if len(day_logs) == 1 and d_date == datetime.now().date():
                            calculated_early_minutes = 0 # Hôm nay có 1 lần chấm -> Đang làm việc, chưa tính về sớm
                        else:
                            if last_log.check_in_time < std_out_dt:
                                calculated_early_minutes = int((std_out_dt - last_log.check_in_time).total_seconds() / 60)

        # Nội suy trạng thái tổng quát (dùng cho backend logic nếu cần)
        statuses = []
        if calculated_late_minutes and int(calculated_late_minutes) > 0:
            statuses.append("Đi muộn")
            
        if calculated_early_minutes and calculated_early_minutes != "Waiting" and int(calculated_early_minutes) > 0:
            statuses.append("Về sớm")
            
        if statuses:
            status = " & ".join(statuses)
        else:
            status = "Đúng giờ"

        # Lấy record đại diện có lời giải trình hoặc bị gian lận
        rep_log = first_log
        for log in day_logs:
            if log.is_fraud or log.explanation_status:
                rep_log = log
                break

        shift_display_name = shift_cat.shift_name if shift_cat else ""

        result.append({
            "id": rep_log.id,
            "username": uname,
            "full_name": display_name,
            "date": date_str,
            "scan_time": time_str,
            "late_minutes": calculated_late_minutes,
            "early_minutes": calculated_early_minutes,
            "is_shift_assigned": is_shift_assigned,
            "shift_display_code": shift_display_code,
            "shift_display_name": shift_display_name,
            "status": status,
            "confidence": rep_log.confidence,
            "image_path": rep_log.image_path,
            "explanation_status": rep_log.explanation_status,
            "explanation_reason": rep_log.explanation_reason,
            "is_fraud": bool(rep_log.is_fraud), 
            "fraud_note": rep_log.fraud_note or "",
            "client_ip": rep_log.client_ip or "",
            "latitude": rep_log.latitude,
            "longitude": rep_log.longitude,
            "attendance_type": rep_log.attendance_type,
            "note": rep_log.note or ""
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