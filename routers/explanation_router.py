from fastapi import APIRouter, Depends, HTTPException, Query, File, UploadFile, Form
from sqlalchemy.orm import Session
from sqlalchemy import cast, Date, and_, or_
from typing import Optional, List
from datetime import date, datetime, timedelta
import os
import shutil
import uuid

from database import get_db
from models import Explanation, Employee, ShiftAssignment, ShiftCategory, Attendance
from schemas import PaginatedExplanationResponse
from routers.auth_router import get_current_user

router = APIRouter()

# ==========================================
# CẤU HÌNH THƯ MỤC LƯU ẢNH
# ==========================================
UPLOAD_DIR = "static/uploads/explanations"
os.makedirs(UPLOAD_DIR, exist_ok=True)

def save_uploaded_file(upload_file: UploadFile) -> str:
    """Hàm hỗ trợ lưu file và trả về đường dẫn"""
    if not upload_file:
        return None
    
    # Lấy đuôi file (vd: .jpg, .png)
    file_extension = upload_file.filename.split(".")[-1]
    file_name = f"{uuid.uuid4()}.{file_extension}"
    file_path = os.path.join(UPLOAD_DIR, file_name)
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(upload_file.file, buffer)
        
    # Chuyển đổi dấu \ thành / để đường dẫn chuẩn xác trên mọi HĐH
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

    # 3. Phân quyền truy cập
    user_role = current_user.get("role")
    user_name = current_user.get("username")
    user_dept = current_user.get("department_id")

    if user_role == "user":
        query = query.filter(Explanation.username == user_name)
    elif user_role == "manager":
        if user_dept:
            subquery = db.query(Employee.username).filter(Employee.department_id == user_dept)
            query = query.filter(
                or_(
                    Explanation.username == user_name,
                    Explanation.username.in_(subquery)
                )
            )
        else:
            query = query.filter(Explanation.username == user_name)
    elif user_role != "admin":
        raise HTTPException(status_code=403, detail="Quyền truy cập bị từ chối")

    # 4. Thực hiện đếm và lấy dữ liệu
    total_records = query.count()
    
    if limit is not None and limit > 0:
        results = query.offset(skip).limit(limit).all()
    else:
        results = query.offset(skip).all()

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
    status: str = Form(...), # Thêm trường status vì schema cũ có
    attached_file: Optional[UploadFile] = File(None), # Nhận file ảnh
    db: Session = Depends(get_db)
):
    # --- 1. KIỂM TRA RÀNG BUỘC TRÙNG LẶP (1 ca/ngày/người) ---
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

    # --- 2. VALIDATE DATE ---
    today = date.today()
    if date >= today:
        raise HTTPException(status_code=400, detail="Chỉ có thể giải trình cho các ngày trong quá khứ.")

    # --- 3. LƯU ẢNH (NẾU CÓ) ---
    file_path = save_uploaded_file(attached_file)

    # --- 4. LƯU DATABASE ---
    try:
        new_explanation = Explanation(
            username=username,
            date=date,
            shift_code=shift_code,
            reason=reason,
            status=status,
            attached_file=file_path # Lưu đường dẫn
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
    if current_user.get("role") not in ["manager", "admin"]:
        raise HTTPException(status_code=403, detail="Không có quyền")

    explanation = db.query(Explanation).filter(Explanation.id == exp_id).first()
    if not explanation:
        raise HTTPException(status_code=404, detail="Không tìm thấy")

    explanation.status = "2" # APPROVED (Đã sửa lại comment và message cho đúng logic)
    db.commit()
    return {"status": "success", "message": "Đã duyệt"}


@router.put("/api/explanations/{exp_id}/reject")
def reject_explanation(exp_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    if current_user.get("role") not in ["manager", "admin"]:
        raise HTTPException(status_code=403, detail="Không có quyền")

    explanation = db.query(Explanation).filter(Explanation.id == exp_id).first()
    if not explanation:
        raise HTTPException(status_code=404, detail="Không tìm thấy")

    explanation.status = "3" # REJECTED
    db.commit()
    return {"status": "success", "message": "Đã từ chối"}


@router.put("/api/explanations/{exp_id}")
def update_explanation(
    exp_id: int, 
    date: Optional[date] = Form(None),
    reason: Optional[str] = Form(None),
    shift_code: Optional[str] = Form(None),
    attached_file: Optional[UploadFile] = File(None), # Nhận file ảnh mới
    db: Session = Depends(get_db), 
    current_user: dict = Depends(get_current_user)
):
    explanation = db.query(Explanation).filter(Explanation.id == exp_id).first()
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
            
        # Cập nhật ảnh nếu user upload ảnh mới
        if attached_file:
            # (Tùy chọn: có thể viết thêm logic xóa file cũ bằng os.remove)
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