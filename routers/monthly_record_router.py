# --- 1. IMPORT CÁC THƯ VIỆN CHUẨN (STANDARD LIBS) ---
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import date, datetime, time, timedelta
from typing import Optional, List

# --- 2. IMPORT CÁC THÀNH PHẦN NỘI BỘ (PROJECT MODULES) ---
from database import get_db
import models
import schemas
import constants
import service.attendace_service as attendance_service

# Khai báo router
router = APIRouter(prefix="/api/monthly-records", tags=["Sync Data"])

@router.get("/sync-create-monthly", status_code=201)
def sync_monthly_records(
    start_date: date = Query(..., description="Ngày bắt đầu (YYYY-MM-DD)"),
    end_date: date = Query(..., description="Ngày kết thúc (YYYY-MM-DD)"),
    username: Optional[str] = Query(None, description="Username lọc theo LIKE (để trống để chốt tất cả)"),
    db: Session = Depends(get_db)
):
    start_dt = datetime.combine(start_date, time.min)
    end_dt = datetime.combine(end_date, time.max)

    query = db.query(models.Attendance).filter(
        models.Attendance.check_in_time >= start_dt,
        models.Attendance.check_in_time <= end_dt
    )
    if username:
        query = query.filter(models.Attendance.username.like(f"%{username}%"))

    raw_data = query.all()

    if not raw_data:
        raise HTTPException(
            status_code=404, 
            detail=f"Không tìm thấy dữ liệu chấm công từ {start_date} đến {end_date}."
        )
    try:
        calculated_records = attendance_service.process_attendance_to_monthly(db, raw_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi logic tính toán: {str(e)}")

    synced_count = 0
    try:
        for rec in calculated_records:
            # Kiểm tra xem ngày đó của nhân viên đó đã có bản ghi chưa
            existing = db.query(models.MonthlyRecord).filter(
                models.MonthlyRecord.employee_id == rec.employee_id,
                models.MonthlyRecord.date == rec.date
            ).first()

            if existing:
                # Nếu đã tồn tại -> Cập nhật (Update)
                existing.shift_code = rec.shift_code
                existing.checkin_time = rec.checkin_time
                existing.checkout_time = rec.checkout_time
                existing.status = rec.status
                existing.late_minutes = rec.late_minutes
                existing.early_minutes = rec.early_minutes
                existing.checkin_image_path = rec.checkin_image_path
                existing.checkout_image_path = rec.checkout_image_path
                existing.note = f"Updated via Sync at {datetime.now().strftime('%H:%M:%S')}"
            else:
                # Nếu chưa có -> Thêm mới (Insert)
                db.add(rec)
            
            synced_count += 1
        
        # Lưu tất cả thay đổi vào Database
        db.commit()
        
        return {
            "status": "success",
            "message": f"Đồng bộ hoàn tất.",
            "data": {
                "total_processed": synced_count,
                "range": f"{start_date} to {end_date}"
            }
        }

    except Exception as e:
        db.rollback() # Hoàn tác nếu có lỗi xảy ra trong quá trình lưu
        raise HTTPException(status_code=500, detail=f"Lỗi Database: {str(e)}")
    
    
from routers.auth_router import get_current_user

@router.get("", response_model=list[schemas.MonthlyRecordOut])
def get_monthly_report(
    start_date: date = Query(..., alias="startDate"),
    end_date: date = Query(..., alias="endDate"),
    employee_id: Optional[int] = Query(None, alias="employee_id"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    role = current_user.get("role", "user")
    current_username = current_user.get("username")
    
    # 1. Authorize access based on role
    allowed_emp_ids = None
    if role == "user":
        emp = db.query(models.Employee).filter(models.Employee.username == current_username).first()
        if not emp:
            return []
        employee_id = emp.id
        allowed_emp_ids = [emp.id]
    elif role == "manager":
        manager = db.query(models.Employee).filter(models.Employee.username == current_username).first()
        if not manager or not manager.department_id:
            return []
        dept_users = db.query(models.Employee.id).filter(models.Employee.department_id == manager.department_id).all()
        allowed_emp_ids = [u[0] for u in dept_users]
        if employee_id and employee_id not in allowed_emp_ids:
            return []
    
    # If employee_id is specifically requested (by Admin/Manager for a specific person)
    if employee_id is not None:
        employee = db.query(models.Employee).filter(models.Employee.id == employee_id).first()
        if not employee:
            raise HTTPException(status_code=404, detail="Nhân viên không tồn tại")
    
    # 2. Get records using the hybrid service
    records = attendance_service.get_hybrid_monthly_records(
        db, 
        start_date, 
        end_date, 
        employee_id
    )
    
    # 3. If it was a bulk query (employee_id is None) and role is Manager, filter by department
    if employee_id is None and allowed_emp_ids is not None:
         records = [r for r in records if r.employee_id in allowed_emp_ids]

    # Cache for performance
    emp_map = {e.id: e for e in db.query(models.Employee).all()}
    shift_map = {s.shift_code: s for s in db.query(models.ShiftCategory).all()}
    
    results = []
    for r in records:
        emp = emp_map.get(r.employee_id)
        sc = shift_map.get(r.shift_code)
        
        # Build enriched record
        record_dict = {
            "id": getattr(r, "id", None),
            "employee_id": r.employee_id,
            "shift_code": r.shift_code,
            "date": r.date,
            "checkin_time": r.checkin_time,
            "checkout_time": r.checkout_time,
            "late_minutes": r.late_minutes,
            "early_minutes": r.early_minutes,
            "status": r.status,
            "explanation_reason": r.explanation_reason,
            "explanation_status": r.explanation_status,
            "checkin_image_path": r.checkin_image_path,
            "checkout_image_path": r.checkout_image_path,
            "note": r.note,
            "full_name": emp.full_name if emp else "Unknown",
            "username": emp.username if emp else "Unknown",
            "shift_display_name": sc.shift_name if sc else (r.shift_code or "Unknown")
        }
        results.append(record_dict)
        
    return results


@router.get("/calculate-monthly-records")
def get_calculated_monthly_records(
    start_date: date = Query(..., description="Ngày bắt đầu (YYYY-MM-DD)"),
    end_date: date = Query(..., description="Ngày kết thúc (YYYY-MM-DD)"),
    username: str = Query(None, description="Lọc theo username cụ thể (tùy chọn)"),
    db: Session = Depends(get_db)
):
    # 1. Truy vấn dữ liệu Attendance thô từ Database
    query = db.query(models.Attendance).filter(
        models.Attendance.check_in_time >= datetime.combine(start_date, time.min),
        models.Attendance.check_in_time <= datetime.combine(end_date, time.max)
    )
    
    if username:
        query = query.filter(models.Attendance.username == username)
    
    raw_attendance = query.all()

    if not raw_attendance:
        raise HTTPException(status_code=404, detail="Không tìm thấy dữ liệu chấm công trong khoảng thời gian này.")
    return attendance_service.process_attendance_to_monthly(db, raw_attendance)

@router.get("/summary", response_model=list[schemas.AttendanceSummaryByEmployee])
def get_attendance_summary_endpoint(
    start_date: date = Query(..., alias="startDate"),
    end_date:   date = Query(..., alias="endDate"),
    username:   Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    role             = current_user.get("role", "user")
    current_username = current_user.get("username")

    target_employee_id = None
    allowed_emp_ids    = None

    if role == "user":
        emp = db.query(models.Employee).filter(
            models.Employee.username == current_username
        ).first()
        if not emp:
            return []
        target_employee_id = emp.id
        allowed_emp_ids    = {emp.id}

    elif role == "manager":
        manager = db.query(models.Employee).filter(
            models.Employee.username == current_username
        ).first()
        if not manager or not manager.department_id:
            return []

        allowed_emp_ids = {
            row[0] for row in db.query(models.Employee.id).filter(
                models.Employee.department_id == manager.department_id
            ).all()
        }

        if username:
            specific = db.query(models.Employee).filter(
                models.Employee.username == username
            ).first()
            if not specific or specific.id not in allowed_emp_ids:
                return []
            target_employee_id = specific.id

    else:  # admin
        if username:
            specific = db.query(models.Employee).filter(
                models.Employee.username == username
            ).first()
            if not specific:
                return []
            target_employee_id = specific.id

    return attendance_service.get_attendance_summary(
        db          = db,
        start_date  = start_date,
        end_date    = end_date,
        employee_id = target_employee_id,
        allowed_emp_ids = allowed_emp_ids,
    )