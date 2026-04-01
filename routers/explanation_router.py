from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import cast, Date, and_
from typing import Optional, List
from datetime import date, datetime, timedelta

from database import get_db
from models import Explanation, Employee, ShiftAssignment, ShiftCategory, Attendance
from schemas import PaginatedExplanationResponse, ExplanationCreate, ExplanationUpdate
from routers.auth_router import get_current_user

router = APIRouter()

@router.get("/api/explanations", response_model=PaginatedExplanationResponse)
def get_explanations(
    status: Optional[str] = Query(None, description="Lọc theo trạng thái"),
    username: Optional[str] = Query(None, description="Tìm kiếm theo username"),
    skip: int = Query(0, ge=0, description="Số bản ghi bỏ qua"),
    limit: int = Query(10, le=100, description="Số bản ghi tối đa trên 1 trang"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    # 1. Khởi tạo query và Join với ShiftCategory để lấy shift_name
    query = db.query(
        Explanation,
        ShiftCategory.shift_name
    ).join(
        ShiftCategory, 
        Explanation.shift_code == ShiftCategory.shift_code, 
        isouter=True
    )

    # 2. Xử lý lọc theo status và username
    if status:
        query = query.filter(Explanation.status == status)
    if username:
        query = query.filter(Explanation.username.ilike(f"%{username}%"))

    # 3. Phân quyền truy cập
    user_role = current_user.get("role")
    user_name = current_user.get("username")
    user_dept = current_user.get("department_id")

    if user_role == "user":
        query = query.filter(Explanation.username == user_name)
    elif user_role == "manager":
        subquery = db.query(Employee.username).filter(Employee.department_id == user_dept)
        query = query.filter(Explanation.username.in_(subquery))
    elif user_role != "admin":
        raise HTTPException(status_code=403, detail="Quyền truy cập bị từ chối")

    # 4. Thực hiện đếm và lấy dữ liệu
    total_records = query.count()
    results = query.offset(skip).limit(limit).all()

    # 5. Map dữ liệu để trả về shift_name trực tiếp trong item
    items = []
    for exp, s_name in results:
        # Chuyển object model sang dict và chèn thêm shift_name
        item_dict = {c.name: getattr(exp, c.name) for c in exp.__table__.columns}
        item_dict["shift_name"] = s_name or exp.shift_code
        items.append(item_dict)

    return {
        "total": total_records,
        "items": items,
        "skip": skip,
        "limit": limit
    }

@router.post("/api/explanations")
def create_explanation(expl: ExplanationCreate, db: Session = Depends(get_db)):
    # --- 1. KIỂM TRA RÀNG BUỘC TRÙNG LẶP (1 ca/ngày/người) ---
    existing = db.query(Explanation).filter(
        and_(
            Explanation.username == expl.username,
            Explanation.date == expl.date,
            Explanation.shift_code == expl.shift_code
        )
    ).first()

    if existing:
        raise HTTPException(
            status_code=400, 
            detail=f"Đã tồn tại giải trình cho ca {expl.shift_code} vào ngày {expl.date}. Mỗi ca chỉ được giải trình một lần."
        )

    # --- 2. VALIDATE DATE ---
    today = date.today()
    if expl.date >= today:
        raise HTTPException(status_code=400, detail="Chỉ có thể giải trình cho các ngày trong quá khứ.")
    # if expl.date.month != today.month or expl.date.year != today.year:
    #     raise HTTPException(status_code=400, detail="Chỉ có thể giải trình trong tháng hiện tại.")

    # --- 3. LƯU DATABASE ---
    try:
        new_explanation = Explanation(**expl.dict())
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

    explanation.status = "2" # REJECTED
    db.commit()
    return {"status": "success", "message": "Đã từ chối"}

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
def update_explanation(exp_id: int, expl_update: ExplanationUpdate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    explanation = db.query(Explanation).filter(Explanation.id == exp_id).first()
    if not explanation:
        raise HTTPException(status_code=404, detail="Không tìm thấy")

    if explanation.username != current_user.get("username"):
        raise HTTPException(status_code=403, detail="Không có quyền sửa")

    if str(explanation.status) != "1":
        raise HTTPException(status_code=400, detail="Chỉ được sửa khi đang chờ duyệt")

    try:
        explanation.date = expl_update.date
        explanation.reason = expl_update.reason
        if expl_update.shift_code:
            explanation.shift_code = expl_update.shift_code
        db.commit()
        return {"status": "success", "message": "Cập nhật thành công"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/shift-categories")
def get_shift_categories(db: Session = Depends(get_db)):
    return db.query(ShiftCategory).all()