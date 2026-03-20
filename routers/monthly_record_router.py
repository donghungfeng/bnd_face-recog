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
    
    
@router.get("", response_model=list[schemas.MonthlyRecordBase])
def get_monthly_report(
    start_date: date = Query(..., alias="startDate"),
    end_date: date = Query(..., alias="endDate"),
    employee_id: int = Query(..., alias="employee_id"),
    db: Session = Depends(get_db)
):
    # 1. Tìm username tương ứng với employee_id (Vì bảng Attendance dùng username)
    employee = db.query(models.Employee).filter(models.Employee.id == employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Nhân viên không tồn tại")
    
    # 2. Gọi hàm xử lý Hybrid
    records = attendance_service.get_hybrid_monthly_records(
        db, 
        start_date, 
        end_date, 
        employee_id
    )
    
    return records


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