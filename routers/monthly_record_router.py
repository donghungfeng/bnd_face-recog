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
from routers.auth_router import get_current_user

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

@router.get("", response_model=list[schemas.MonthlyRecordOut])
def get_monthly_report(
    start_date: date = Query(..., alias="startDate"),
    end_date: date = Query(..., alias="endDate"),
    employee_id: Optional[int] = Query(None, alias="employee_id"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    current_username = current_user.get("username")

    # ==========================================
    # 1. TÌM THÔNG TIN USER VÀ QUYỀN TỪ DATABASE
    # ==========================================
    me = db.query(models.Employee).filter(models.Employee.username == current_username).first()
    if not me:
        return []

    # Lấy danh sách phòng ban & quyền
    my_departments = db.query(models.EmployeeDepartment).filter(
        models.EmployeeDepartment.employee_id == me.id
    ).all()
    
    # Kiểm tra quyền admin
    is_admin = any(dept.role and dept.role.lower() == "admin" for dept in my_departments)

    # ==========================================
    # 2. XÁC ĐỊNH DANH SÁCH NHÂN VIÊN ĐƯỢC PHÉP XEM
    # ==========================================
    allowed_emp_ids = None

    if not is_admin:
        # Mặc định: Luôn được xem bản ghi của chính mình
        allowed_emp_ids = {me.id}
        
        # Tìm các ID phòng ban mà user này làm manager
        managed_dept_ids = [
            dept.department_id for dept in my_departments 
            if dept.role and dept.role.lower() == "manager" 
        ]
        
        if managed_dept_ids:
            # Lấy ID của tất cả nhân sự thuộc các phòng ban đang quản lý
            managed_emps = db.query(models.EmployeeDepartment.employee_id).filter(
                models.EmployeeDepartment.department_id.in_(managed_dept_ids)
            ).all()
            for row in managed_emps:
                allowed_emp_ids.add(row[0])

    # ==========================================
    # 3. XỬ LÝ YÊU CẦU TÌM CỤ THỂ 1 EMPLOYEE_ID
    # ==========================================
    if employee_id is not None:
        employee = db.query(models.Employee).filter(models.Employee.id == employee_id).first()
        if not employee:
            raise HTTPException(status_code=404, detail="Nhân viên không tồn tại")
        
        # Lớp khiên bảo mật: Chặn nếu không có quyền quản lý ID này
        if allowed_emp_ids is not None and employee_id not in allowed_emp_ids:
            return []

    # ==========================================
    # 4. TRUY VẤN DỮ LIỆU TỪ SERVICE
    # ==========================================
    records = attendance_service.get_hybrid_monthly_records(
        db, 
        start_date, 
        end_date, 
        employee_id
    )
    
    # Lớp khiên số 2: Nếu truy vấn hàng loạt (bulk), phải lọc rác những người không thuộc quyền
    if employee_id is None and allowed_emp_ids is not None:
        records = [r for r in records if r.employee_id in allowed_emp_ids]

    # ==========================================
    # 5. RENDER DỮ LIỆU ĐỂ TRẢ VỀ FRONTEND
    # ==========================================
    # Cache lại để tối ưu vòng lặp
    emp_map = {e.id: e for e in db.query(models.Employee).all()}
    shift_map = {s.shift_code: s for s in db.query(models.ShiftCategory).all()}
    
    results = []
    for r in records:
        emp = emp_map.get(r.employee_id)
        sc = shift_map.get(r.shift_code)
        
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
            "actual_hours": r.actual_hours,
            "actual_workday": r.actual_workday,
            "note": r.note,
            "full_name": emp.full_name if emp else "Unknown",
            "username": emp.username if emp else "Unknown",
            "shift_display_name": sc.shift_name if sc else (r.shift_code or "Unknown"),
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
    current_username = current_user.get("username")

    target_employee_id = None
    allowed_emp_ids    = None

    # ==========================================
    # 1. TÌM THÔNG TIN USER VÀ QUYỀN TỪ DATABASE
    # ==========================================
    me = db.query(models.Employee).filter(
        models.Employee.username == current_username
    ).first()
    if not me:
        return []

    # Lấy danh sách phòng ban & quyền
    my_departments = db.query(models.EmployeeDepartment).filter(
        models.EmployeeDepartment.employee_id == me.id
    ).all()
    
    # Kiểm tra quyền admin
    is_admin = any(dept.role and dept.role.lower() == "admin" for dept in my_departments)

    # ==========================================
    # 2. ÁP DỤNG PHÂN QUYỀN VÀ LỌC TẬP DỮ LIỆU
    # ==========================================
    if not is_admin:
        # Mặc định: Tập hợp allowed_emp_ids luôn chứa ID của chính mình
        allowed_emp_ids = {me.id}

        # Tìm các ID phòng ban mà user này làm manager
        managed_dept_ids = [
            dept.department_id for dept in my_departments 
            if dept.role and dept.role.lower() == "manager" 
        ]

        if managed_dept_ids:
            # Lấy tất cả employee_id thuộc các phòng ban quản lý
            managed_emps = db.query(models.EmployeeDepartment.employee_id).filter(
                models.EmployeeDepartment.department_id.in_(managed_dept_ids)
            ).all()
            
            for row in managed_emps:
                allowed_emp_ids.add(row[0])

        # Nếu request yêu cầu xem 1 username cụ thể
        if username:
            specific = db.query(models.Employee).filter(
                models.Employee.username == username
            ).first()
            
            # Chặn đứng nếu username đó không tồn tại HOẶC không nằm trong ds được phép quản lý
            if not specific or specific.id not in allowed_emp_ids:
                return []
                
            target_employee_id = specific.id

    else:  
        # is_admin == True -> Bỏ qua kiểm tra allowed_emp_ids (mặc định = None để lấy tất)
        if username:
            specific = db.query(models.Employee).filter(
                models.Employee.username == username
            ).first()
            if not specific:
                return []
            target_employee_id = specific.id

    # ==========================================
    # 3. GỌI SERVICE XỬ LÝ NGHIỆP VỤ
    # ==========================================
    return attendance_service.get_attendance_summary(
        db          = db,
        start_date  = start_date,
        end_date    = end_date,
        employee_id = target_employee_id,
        allowed_emp_ids = allowed_emp_ids,
    )