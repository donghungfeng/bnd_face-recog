from fastapi import APIRouter, Depends, HTTPException, Query, File, UploadFile, Form
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from typing import Optional
from datetime import date, datetime
import os
import shutil
import uuid

# Import models, schemas và cấu hình DB
from database import get_db
from models import ShiftSwapRequest, Employee, EmployeeDepartment
from schemas import PaginatedShiftSwapResponse
from routers.auth_router import get_current_user # Nhớ import hàm check token của bạn

router = APIRouter(
    tags=["Shift Swap"]
)

# ==========================================
# CẤU HÌNH THƯ MỤC LƯU ẢNH
# ==========================================
UPLOAD_DIR = "data/shift_swap_images"
os.makedirs(UPLOAD_DIR, exist_ok=True)

def save_uploaded_file(upload_file: UploadFile) -> Optional[str]:
    if not upload_file:
        return None
    
    dated_dir = os.path.join(UPLOAD_DIR, datetime.now().strftime("%Y_%m_%d"))
    os.makedirs(dated_dir, exist_ok=True)

    file_extension = upload_file.filename.split(".")[-1]
    file_name = f"{uuid.uuid4()}.{file_extension}"
    file_path = os.path.join(dated_dir, file_name)
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(upload_file.file, buffer)
        
    return file_path.replace("\\", "/")

# ==========================================
# API ENDPOINTS
# ==========================================

@router.get("/api/shift-swaps", response_model=PaginatedShiftSwapResponse)
def get_shift_swaps(
    status: Optional[str] = Query(None, description="Lọc theo trạng thái (PENDING, APPROVED, REJECTED)"),
    start_date: Optional[date] = Query(None, description="Từ ngày (áp dụng cho source_date)"),
    end_date: Optional[date] = Query(None, description="Đến ngày (áp dụng cho source_date)"),
    skip: int = Query(0, ge=0),
    limit: Optional[int] = Query(None), 
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    current_username = current_user.get("username")
    
    # Lấy thông tin user hiện tại
    me = db.query(Employee).filter(Employee.username == current_username).first()
    if not me:
        raise HTTPException(status_code=403, detail="Tài khoản không tồn tại")

    # Khởi tạo query
    query = db.query(ShiftSwapRequest)

    # Lọc theo tham số truyền vào
    if status:
        query = query.filter(ShiftSwapRequest.status == status)
    if start_date:
        query = query.filter(ShiftSwapRequest.source_date >= start_date)
    if end_date:
        query = query.filter(ShiftSwapRequest.source_date <= end_date)

    # ==========================================
    # PHÂN QUYỀN TRUY CẬP TRẢ DỮ LIỆU
    # ==========================================
    my_departments = db.query(EmployeeDepartment).filter(EmployeeDepartment.employee_id == me.id).all()
    is_admin = any(dept.role and dept.role.lower() == "admin" for dept in my_departments)

    if not is_admin:
        allowed_emp_ids = {me.id} # Luôn thấy đơn của chính mình
        
        # Nếu là manager, lấy danh sách ID nhân viên thuộc phòng ban mình quản lý
        managed_dept_ids = [dept.department_id for dept in my_departments if dept.role and dept.role.lower() == "manager"]
        if managed_dept_ids:
            dept_users = db.query(EmployeeDepartment.employee_id).filter(
                EmployeeDepartment.department_id.in_(managed_dept_ids)
            ).all()
            for u in dept_users:
                allowed_emp_ids.add(u[0])

        # Áp dụng filter: Chỉ lấy đơn mà source hoặc target thuộc danh sách được phép thấy
        query = query.filter(
            or_(
                ShiftSwapRequest.employee_source_id.in_(list(allowed_emp_ids)),
                ShiftSwapRequest.employee_target_id.in_(list(allowed_emp_ids))
            )
        )

    # Đếm và phân trang
    total_records = query.count()
    if limit is not None and limit > 0:
        results = query.order_by(ShiftSwapRequest.id.desc()).offset(skip).limit(limit).all()
    else:
        results = query.order_by(ShiftSwapRequest.id.desc()).offset(skip).all()

    return {
        "total": total_records,
        "items": results,
        "skip": skip,
        "limit": limit if limit is not None else total_records 
    }


@router.post("/api/shift-swaps")
def create_shift_swap(
    source_date: date = Form(...),
    target_date: date = Form(...),
    employee_target_id: Optional[int] = Form(None),
    source_shift_code: Optional[str] = Form(None),
    target_shift_code: Optional[str] = Form(None),
    is_all_day: int = Form(0),
    reason: Optional[str] = Form(None),
    attached_file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    # Tự động lấy người tạo đơn là user đang login (Bảo mật: không cho truyền từ Form)
    me = db.query(Employee).filter(Employee.username == current_user.get("username")).first()
    if not me:
        raise HTTPException(status_code=403, detail="Tài khoản không tồn tại")

    # Ràng buộc thời gian (VD: Không cho đổi ca trong quá khứ)
    # today = date.today()
    # if source_date < today or target_date < today:
    #     raise HTTPException(status_code=400, detail="Không thể tạo yêu cầu đổi ca cho những ngày trong quá khứ.")

    file_path = save_uploaded_file(attached_file)

    try:
        new_swap = ShiftSwapRequest(
            employee_source_id=me.id,  # Gắn ID của người đang login
            employee_target_id=employee_target_id,
            source_date=source_date,
            target_date=target_date,
            source_shift_code=source_shift_code,
            target_shift_code=target_shift_code,
            is_all_day=is_all_day,
            reason=reason,
            status="PENDING",
            attached_file=file_path
        )
        db.add(new_swap)
        db.commit()
        db.refresh(new_swap)
        return {"status": "success", "message": "Tạo yêu cầu đổi ca thành công", "data": new_swap}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Lỗi lưu dữ liệu: {str(e)}")


@router.put("/api/shift-swaps/{swap_id}")
def update_shift_swap(
    swap_id: int, 
    employee_target_id: Optional[int] = Form(None),
    source_date: Optional[date] = Form(None),
    target_date: Optional[date] = Form(None),
    source_shift_code: Optional[str] = Form(None),
    target_shift_code: Optional[str] = Form(None),
    is_all_day: Optional[int] = Form(None),
    reason: Optional[str] = Form(None),
    attached_file: Optional[UploadFile] = File(None), 
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    me = db.query(Employee).filter(Employee.username == current_user.get("username")).first()
    swap_req = db.query(ShiftSwapRequest).filter(ShiftSwapRequest.id == swap_id).first()
    
    if not swap_req:
        raise HTTPException(status_code=404, detail="Không tìm thấy yêu cầu đổi ca")

    # Chỉ người tạo mới được sửa đơn của mình
    if swap_req.employee_source_id != me.id:
        raise HTTPException(status_code=403, detail="Bạn không có quyền sửa yêu cầu này")

    if swap_req.status != "PENDING":
        raise HTTPException(status_code=400, detail="Chỉ được sửa đơn khi đang ở trạng thái Chờ duyệt (PENDING)")

    try:
        if employee_target_id is not None: swap_req.employee_target_id = employee_target_id
        if source_date is not None: swap_req.source_date = source_date
        if target_date is not None: swap_req.target_date = target_date
        if source_shift_code is not None: swap_req.source_shift_code = source_shift_code
        if target_shift_code is not None: swap_req.target_shift_code = target_shift_code
        if is_all_day is not None: swap_req.is_all_day = is_all_day
        if reason is not None: swap_req.reason = reason
            
        if attached_file:
            swap_req.attached_file = save_uploaded_file(attached_file)

        db.commit()
        return {"status": "success", "message": "Cập nhật yêu cầu thành công"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/api/shift-swaps/{swap_id}/approve")
def approve_shift_swap(swap_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    me = db.query(Employee).filter(Employee.username == current_user.get("username")).first()
    swap_req = db.query(ShiftSwapRequest).filter(ShiftSwapRequest.id == swap_id).first()
    
    if not swap_req:
        raise HTTPException(status_code=404, detail="Không tìm thấy yêu cầu")
    if swap_req.status != "PENDING":
        raise HTTPException(status_code=400, detail="Yêu cầu này đã được xử lý")

    # KIỂM TRA QUYỀN DUYỆT CHẶT CHẼ
    my_departments = db.query(EmployeeDepartment).filter(EmployeeDepartment.employee_id == me.id).all()
    is_admin = any(dept.role and dept.role.lower() == "admin" for dept in my_departments)

    if not is_admin:
        managed_dept_ids = [d.department_id for d in my_departments if d.role and d.role.lower() == "manager"]
        if not managed_dept_ids:
            raise HTTPException(status_code=403, detail="Không có quyền quản lý")
            
        # Manager chỉ duyệt được nếu người xin đổi (source) nằm trong phòng ban của Manager
        has_rights = db.query(EmployeeDepartment).filter(
            EmployeeDepartment.employee_id == swap_req.employee_source_id,
            EmployeeDepartment.department_id.in_(managed_dept_ids)
        ).first()
        
        if not has_rights:
            raise HTTPException(status_code=403, detail="Bạn không quản lý nhân viên này, không thể duyệt.")

    swap_req.status = "APPROVED"
    swap_req.approved_by_id = me.id # Lưu vết người duyệt
    db.commit()
    return {"status": "success", "message": "Đã duyệt yêu cầu đổi ca"}


@router.put("/api/shift-swaps/{swap_id}/reject")
def reject_shift_swap(swap_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    me = db.query(Employee).filter(Employee.username == current_user.get("username")).first()
    swap_req = db.query(ShiftSwapRequest).filter(ShiftSwapRequest.id == swap_id).first()
    
    if not swap_req:
        raise HTTPException(status_code=404, detail="Không tìm thấy yêu cầu")
    if swap_req.status != "PENDING":
        raise HTTPException(status_code=400, detail="Yêu cầu này đã được xử lý")

    # KIỂM TRA QUYỀN DUYỆT
    my_departments = db.query(EmployeeDepartment).filter(EmployeeDepartment.employee_id == me.id).all()
    is_admin = any(dept.role and dept.role.lower() == "admin" for dept in my_departments)

    if not is_admin:
        managed_dept_ids = [d.department_id for d in my_departments if d.role and d.role.lower() == "manager"]
        if not managed_dept_ids:
            raise HTTPException(status_code=403, detail="Không có quyền quản lý")
            
        has_rights = db.query(EmployeeDepartment).filter(
            EmployeeDepartment.employee_id == swap_req.employee_source_id,
            EmployeeDepartment.department_id.in_(managed_dept_ids)
        ).first()
        
        if not has_rights:
            raise HTTPException(status_code=403, detail="Bạn không quản lý nhân viên này, không thể từ chối.")

    swap_req.status = "REJECTED"
    swap_req.approved_by_id = me.id
    db.commit()
    return {"status": "success", "message": "Đã từ chối yêu cầu đổi ca"}