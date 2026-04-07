from fastapi import APIRouter, Query, Request, HTTPException, Depends
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

import models
from database import get_db
from routers.auth_router import get_current_user

router = APIRouter(prefix="/leave-requests", tags=["Leave Requests"])
templates = Jinja2Templates(directory="templates")

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
    search: str = Query(None),
    status: str = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    current_username = current_user.get("username")

    # ==========================================
    # 1. TÌM THÔNG TIN USER VÀ QUYỀN TỪ DATABASE
    # ==========================================
    me = db.query(models.Employee).filter(models.Employee.username == current_username).first()
    if not me:
        return [] # Trả về mảng rỗng

    # Lấy danh sách phòng ban & quyền
    my_departments = db.query(models.EmployeeDepartment).filter(
        models.EmployeeDepartment.employee_id == me.id
    ).all()
    
    # Kiểm tra quyền admin
    is_admin = any(dept.role and dept.role.lower() == "admin" for dept in my_departments)

    query = db.query(models.LeaveRequest)

    # ==========================================
    # 2. ÁP DỤNG PHÂN QUYỀN NẾU KHÔNG PHẢI ADMIN
    # ==========================================
    if not is_admin:
        allowed_usernames = {current_username}
        
        # Tìm các phòng ban đang làm manager
        managed_dept_ids = [
            dept.department_id for dept in my_departments 
            if dept.role and dept.role.lower() == "manager" 
        ]

        if managed_dept_ids:
            dept_users = db.query(models.Employee.username).join(models.EmployeeDepartment).filter(
                models.EmployeeDepartment.department_id.in_(managed_dept_ids)
            ).all()
            
            for u in dept_users:
                allowed_usernames.add(u[0])

        allowed_usernames_list = list(allowed_usernames)

        # Bộ lọc: Thuộc danh sách quản lý HOẶC được chỉ định đích danh duyệt
        query = query.filter(
            or_(
                models.LeaveRequest.username.in_(allowed_usernames_list),
                models.LeaveRequest.approver_username == current_username
            )
        )

    # ==========================================
    # 3. LOGIC LỌC THEO TRẠNG THÁI VÀ TÌM KIẾM
    # ==========================================
    if status:
        query = query.filter(models.LeaveRequest.status == status)

    if search:
        query = query.filter(
            or_(
                models.LeaveRequest.username.ilike(f"%{search}%"),
                models.LeaveRequest.fullname.ilike(f"%{search}%")
            )
        )

    total = query.count()
    total_pages = max(1, (total + size - 1) // size)
    records = query.order_by(models.LeaveRequest.id.desc()).offset((page - 1) * size).limit(size).all()

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
        })

    return {
        "items": results,
        "total": total,
        "total_pages": total_pages,
        "page": page
    }

@router.post("/api")
def create_request(item: LeaveRequestModel, db: Session = Depends(get_db)):
    try:
        # Lấy tên của người duyệt từ DB để lưu cho chuẩn xác
        from models import Employee
        approver = db.query(Employee).filter(Employee.username == item.approver_username).first()
        approver_name = approver.full_name if approver else "Quản lý"

        new_req = models.LeaveRequest(
            username=item.username,
            fullname=item.fullname,
            from_date=item.from_date,
            from_session=item.from_session,
            to_date=item.to_date,
            to_session=item.to_session,
            type_id=item.type_id,
            reason=item.reason,
            approver_username=item.approver_username, # <-- Lưu mã người duyệt
            approver_fullname=approver_name,          # <-- Lưu tên người duyệt
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