import os
import shutil

from fastapi import APIRouter, Form, Query, Request, HTTPException, Depends, UploadFile, File
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

import models
from database import get_db
from routers.auth_router import get_current_user

router = APIRouter(prefix="/leave-requests", tags=["Leave Requests"])
templates = Jinja2Templates(directory="templates")

LEAVE_DIR = "data/leave_requests"
os.makedirs(LEAVE_DIR, exist_ok=True)

# Schema nhận dữ liệu từ Frontend
class LeaveRequestModel(BaseModel):
    username: str
    fullname: str
    from_date: str
    from_session: str
    to_date: str
    to_session: str
    type_id: int
    reason: str
    approver_username: str

class LeaveActionModel(BaseModel):
    status: str # 'APPROVED' hoặc 'REJECTED'
    approver_username: str
    approver_fullname: str

@router.get("/")
async def render_page(request: Request):
    return templates.TemplateResponse("leave_requests.html", {"request": request})

@router.get("/api")
def get_all_requests(
    page: int = 1,
    size: int = 10,
    search: str = Query(None),
    status: str = Query(None), # <--- 1. Bổ sung tham số nhận status
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    current_username = current_user.get("username")
    current_role = current_user.get("role", "user")

    query = db.query(models.LeaveRequest)

    # Phân quyền (RBAC)
    if current_role != "admin":
        query = query.filter(
            or_(
                models.LeaveRequest.username == current_username,
                models.LeaveRequest.approver_username == current_username
            )
        )

    # 2. Logic Lọc theo Trạng thái
    if status:
        query = query.filter(models.LeaveRequest.status == status)

    # 3. Logic Tìm kiếm
    if search:
        query = query.filter(
            or_(
                models.LeaveRequest.username.ilike(f"%{search}%"),
                models.LeaveRequest.fullname.ilike(f"%{search}%")
            )
        )

    # Phân trang
    total = query.count()
    offset = (page - 1) * size
    records = query.order_by(models.LeaveRequest.id.desc()).offset(offset).limit(size).all()
    
    results = []
    for r in records:
        results.append({
            "id": r.id,
            "username": r.username,
            "fullname": r.fullname or "---",
            "type_name": r.leave_type.name if r.leave_type else "Không xác định",
            "from_date": r.from_date.strftime("%d/%m/%Y") if r.from_date else "",
            "from_session": r.from_session,
            "to_date": r.to_date.strftime("%d/%m/%Y") if r.to_date else "",
            "to_session": r.to_session,
            "status": r.status,
            "approver_fullname": r.approver_fullname,
            "attached_image": r.attached_image
        })
        
    return {
        "items": results,
        "total": total,
        "page": page,
        "size": size,
        "total_pages": (total + size - 1) // size if size > 0 else 1
    }

@router.post("/api")
async def create_request(
    username: str = Form(...),
    fullname: str = Form(...),
    from_date: str = Form(...),
    from_session: str = Form(...),
    to_date: str = Form(...),
    to_session: str = Form(...),
    type_id: int = Form(...),
    reason: str = Form(...),
    approver_username: str = Form(...),
    attached_file: UploadFile = File(None), # <--- Tham số nhận file ảnh (không bắt buộc)
    db: Session = Depends(get_db)
):
    try:
        from models import Employee
        # Đã bỏ item. đi, dùng trực tiếp biến approver_username
        approver = db.query(Employee).filter(Employee.username == approver_username).first()
        approver_name = approver.full_name if approver else "Quản lý"

        # --- XỬ LÝ LƯU ẢNH ---
        image_path_db = None
        if attached_file and attached_file.filename:
            import datetime as dt
            now = dt.datetime.now()
            date_folder = now.strftime("%Y-%m-%d")

            base_dir = os.getcwd() 
            save_dir = os.path.join(base_dir, LEAVE_DIR, date_folder)
            os.makedirs(save_dir, exist_ok=True)

            # Đã bỏ item. đi, dùng trực tiếp biến username
            ext = os.path.splitext(attached_file.filename)[1]
            filename = f"{username}_{now.strftime('%H%M%S')}{ext}"
            file_path = os.path.join(save_dir, filename)

            # Lưu file xuống ổ cứng
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(attached_file.file, buffer)

            # Đường dẫn ảo để lưu vào database (chuẩn bị cho việc web đọc)
            image_path_db = f"{LEAVE_DIR}/{date_folder}/{filename}"

        # --- LƯU VÀO DATABASE ---
        new_req = models.LeaveRequest(
            username=username,               # Đã bỏ item.
            fullname=fullname,               # Đã bỏ item.
            from_date=from_date,             # Đã bỏ item.
            from_session=from_session,       # Đã bỏ item.
            to_date=to_date,                 # Đã bỏ item.
            to_session=to_session,           # Đã bỏ item.
            type_id=type_id,                 # Đã bỏ item.
            reason=reason,                   # Đã bỏ item.
            approver_username=approver_username, # Đã bỏ item.
            approver_fullname=approver_name, 
            attached_image=image_path_db, 
            status="PENDING"
        )
        db.add(new_req)
        db.commit()
        return {"status": "success", "message": "Đã tạo đơn xin nghỉ"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Lỗi: {str(e)}")

@router.put("/api/{request_id}/status")
def process_request(request_id: int, action: LeaveActionModel, db: Session = Depends(get_db)):
    try:
        req = db.query(models.LeaveRequest).filter(models.LeaveRequest.id == request_id).first()
        if not req:
            raise HTTPException(status_code=404, detail="Không tìm thấy đơn")
        
        req.status = action.status
        req.approver_username = action.approver_username
        req.approver_fullname = action.approver_fullname
        
        db.commit()
        return {"status": "success", "message": f"Đã {action.status} đơn nghỉ"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Lỗi: {str(e)}")