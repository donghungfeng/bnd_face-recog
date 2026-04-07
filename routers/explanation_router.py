from fastapi import APIRouter, Depends, HTTPException, Query, File, UploadFile, Form
from sqlalchemy.orm import Session
from sqlalchemy import cast, Date, and_, or_
from typing import Optional, List
from datetime import date, datetime, timedelta
import os
import shutil
import uuid

from database import get_db
# BỔ SUNG THÊM EmployeeDepartment
from models import Explanation, Employee, ShiftAssignment, ShiftCategory, Attendance, EmployeeDepartment
from schemas import PaginatedExplanationResponse
from routers.auth_router import get_current_user

router = APIRouter()

# ==========================================
# CẤU HÌNH THƯ MỤC LƯU ẢNH
# ==========================================
UPLOAD_DIR = "data/explanation_db"
os.makedirs(UPLOAD_DIR, exist_ok=True)

def save_uploaded_file(upload_file: UploadFile) -> str:
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

@router.get("/api/explanations", response_model=PaginatedExplanationResponse)
def get_explanations(
    status: Optional[str] = Query(None, description="Lọc theo trạng thái"),
    username: Optional[str] = Query(None, description="Tìm kiếm theo username"),
    start_date: Optional[date] = Query(None, description="Từ ngày"),
    end_date: Optional[date] = Query(None, description="Đến ngày"),
    skip: int = Query(0, ge=0, description="Số bản ghi bỏ qua"),
    limit: Optional[int] = Query(None, description="Số bản ghi tối đa. Bỏ trống để lấy tất cả"), 
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    current_username = current_user.get("username")

    # 1. Khởi tạo query và Join
    query = db.query(
        Explanation,
        ShiftCategory.shift_name
    ).join(
        ShiftCategory, 
        Explanation.shift_code == ShiftCategory.shift_code, 
        isouter=True
    )

    # 2. Xử lý lọc
    if status:
        query = query.filter(Explanation.status == status)
    if username:
        query = query.filter(Explanation.username.ilike(f"%{username}%"))
    if start_date:
        query = query.filter(Explanation.date >= start_date)
    if end_date:
        query = query.filter(Explanation.date <= end_date)

    # ==========================================
    # 3. Phân quyền truy cập bằng EmployeeDepartment
    # ==========================================
    me = db.query(Employee).filter(Employee.username == current_username).first()
    if not me:
        raise HTTPException(status_code=403, detail="Tài khoản không tồn tại")

    my_departments = db.query(EmployeeDepartment).filter(
        EmployeeDepartment.employee_id == me.id
    ).all()
    
    is_admin = any(dept.role and dept.role.lower() == "admin" for dept in my_departments)

    if not is_admin:
        allowed_usernames = {current_username}
        managed_dept_ids = [
            dept.department_id for dept in my_departments 
            if dept.role and dept.role.lower() == "manager" 
        ]

        if managed_dept_ids:
            dept_users = db.query(Employee.username).join(EmployeeDepartment).filter(
                EmployeeDepartment.department_id.in_(managed_dept_ids)
            ).all()
            
            for u in dept_users:
                allowed_usernames.add(u[0])

        query = query.filter(Explanation.username.in_(list(allowed_usernames)))

    # 4. Thực hiện đếm và lấy dữ liệu
    total_records = query.count()
    
    if limit is not None and limit > 0:
        results = query.order_by(Explanation.id.desc()).offset(skip).limit(limit).all()
    else:
        results = query.order_by(Explanation.id.desc()).offset(skip).all()

    # 5. Map dữ liệu để trả về
    items = []
    for exp, s_name in results:
        item_dict = {c.name: getattr(exp, c.name) for c in exp.__table__.columns}
        item_dict["shift_name"] = s_name or exp.shift_code
        items.append(item_dict)

    return {
        "total": total_records,
        "items": items,
        "skip": skip,
        "limit": limit if limit is not None else total_records 
    }


@router.post("/api/explanations")
def create_explanation(
    username: str = Form(...),
    date: date = Form(...),
    shift_code: str = Form(...),
    reason: str = Form(...),
    status: str = Form(...),
    attached_file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    existing = db.query(Explanation).filter(
        and_(
            Explanation.username == username,
            Explanation.date == date,
            Explanation.shift_code == shift_code
        )
    ).first()

    if existing:
        raise HTTPException(
            status_code=400, 
            detail=f"Đã tồn tại giải trình cho ca {shift_code} vào ngày {date}. Mỗi ca chỉ được giải trình một lần."
        )

    today = date.today()
    if date >= today:
        raise HTTPException(status_code=400, detail="Chỉ có thể giải trình cho các ngày trong quá khứ.")

    file_path = save_uploaded_file(attached_file)

    try:
        new_explanation = Explanation(
            username=username,
            date=date,
            shift_code=shift_code,
            reason=reason,
            status=status,
            attached_file=file_path 
        )
        db.add(new_explanation)
        db.commit()
        db.refresh(new_explanation)
        return {"status": "success", "message": "Thêm thành công", "data": new_explanation}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Lỗi lưu dữ liệu: {str(e)}")


@router.put("/api/explanations/{exp_id}/approve")
def approve_explanation(exp_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    current_username = current_user.get("username")
    
    explanation = db.query(Explanation).filter(Explanation.id == exp_id).first()
    if not explanation:
        raise HTTPException(status_code=404, detail="Không tìm thấy")

    # KIỂM TRA QUYỀN DUYỆT CHẶT CHẼ
    me = db.query(Employee).filter(Employee.username == current_username).first()
    my_departments = db.query(EmployeeDepartment).filter(EmployeeDepartment.employee_id == me.id).all()
    is_admin = any(dept.role and dept.role.lower() == "admin" for dept in my_departments)

    if not is_admin:
        managed_dept_ids = [d.department_id for d in my_departments if d.role and d.role.lower() == "manager"]
        if not managed_dept_ids:
            raise HTTPException(status_code=403, detail="Không có quyền quản lý")
            
        # Kiểm tra xem người tạo giải trình có nằm trong phòng ban do người này quản lý không
        target_emp = db.query(Employee).filter(Employee.username == explanation.username).first()
        if target_emp:
            has_rights = db.query(EmployeeDepartment).filter(
                EmployeeDepartment.employee_id == target_emp.id,
                EmployeeDepartment.department_id.in_(managed_dept_ids)
            ).first()
            if not has_rights:
                raise HTTPException(status_code=403, detail="Bạn không quản lý nhân viên này, không thể duyệt.")

    explanation.status = "2" # APPROVED
    db.commit()
    return {"status": "success", "message": "Đã duyệt"}


@router.put("/api/explanations/{exp_id}/reject")
def reject_explanation(exp_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    current_username = current_user.get("username")
    
    explanation = db.query(Explanation).filter(Explanation.id == exp_id).first()
    if not explanation:
        raise HTTPException(status_code=404, detail="Không tìm thấy")

    # KIỂM TRA QUYỀN DUYỆT CHẶT CHẼ
    me = db.query(Employee).filter(Employee.username == current_username).first()
    my_departments = db.query(EmployeeDepartment).filter(EmployeeDepartment.employee_id == me.id).all()
    is_admin = any(dept.role and dept.role.lower() == "admin" for dept in my_departments)

    if not is_admin:
        managed_dept_ids = [d.department_id for d in my_departments if d.role and d.role.lower() == "manager"]
        if not managed_dept_ids:
            raise HTTPException(status_code=403, detail="Không có quyền quản lý")
            
        target_emp = db.query(Employee).filter(Employee.username == explanation.username).first()
        if target_emp:
            has_rights = db.query(EmployeeDepartment).filter(
                EmployeeDepartment.employee_id == target_emp.id,
                EmployeeDepartment.department_id.in_(managed_dept_ids)
            ).first()
            if not has_rights:
                raise HTTPException(status_code=403, detail="Bạn không quản lý nhân viên này, không thể từ chối.")

    explanation.status = "3" # REJECTED
    db.commit()
    return {"status": "success", "message": "Đã từ chối"}


@router.put("/api/explanations/{exp_id}")
def update_explanation(
    exp_id: int, 
    date: Optional[date] = Form(None),
    reason: Optional[str] = Form(None),
    shift_code: Optional[str] = Form(None),
    attached_file: Optional[UploadFile] = File(None), 
    db: Session = Depends(get_db), 
    current_user: dict = Depends(get_current_user)
):
    explanation = db.query(Explanation).filter(Explanation.id == exp_id).first()
    today = date.today()
    if date >= today:
        raise HTTPException(status_code=400, detail="Chỉ có thể giải trình cho các ngày trong quá khứ.")
    if not explanation:
        raise HTTPException(status_code=404, detail="Không tìm thấy")

    if explanation.username != current_user.get("username"):
        raise HTTPException(status_code=403, detail="Không có quyền sửa")

    if str(explanation.status) != "1":
        raise HTTPException(status_code=400, detail="Chỉ được sửa khi đang chờ duyệt")

    try:
        if date:
            explanation.date = date
        if reason:
            explanation.reason = reason
        if shift_code:
            explanation.shift_code = shift_code
            
        if attached_file:
            new_file_path = save_uploaded_file(attached_file)
            explanation.attached_file = new_file_path

        db.commit()
        return {"status": "success", "message": "Cập nhật thành công"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/shift-categories")
def get_shift_categories(db: Session = Depends(get_db)):
    return db.query(ShiftCategory).all()