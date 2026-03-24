from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import cast, Date
from typing import Optional
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
    current_user: dict = Depends(get_current_user) # Đã đổi thành dict để lấy payload từ Token
):
    # 1. Khởi tạo query cơ bản (Lấy tất cả)
    query = db.query(Explanation)

    # 2. Xử lý lọc theo status (nếu client có truyền lên)
    if status:
        query = query.filter(Explanation.status == status)

    # 3. Xử lý logic tìm kiếm theo username (nếu có truyền vào)
    if username:
        query = query.filter(Explanation.username.ilike(f"%{username}%"))

    # 4. Lấy thông tin từ payload của Token
    user_role = current_user.get("role")
    user_name = current_user.get("username")
    user_dept = current_user.get("department_id")

    # 5. Xử lý phân quyền theo Role
    if user_role == "user":
        # User chỉ lấy được bản ghi của chính mình
        query = query.filter(Explanation.username == user_name)
        
    elif user_role == "manager":
        # Manager lấy tất cả nhân sự có cùng department_id
        subquery = db.query(Employee.username).filter(
            Employee.department_id == user_dept
        )
        query = query.filter(Explanation.username.in_(subquery))
        
    elif user_role == "admin":
        # Admin lấy toàn bộ, không cần thêm bộ lọc nào
        pass 
        
    else:
        raise HTTPException(status_code=403, detail="Quyền truy cập bị từ chối")

    # 6. Thực hiện đếm tổng số bản ghi (cho phân trang)
    total_records = query.count()

    # 7. Thực hiện phân trang và lấy dữ liệu
    explanations = query.offset(skip).limit(limit).all()

    return {
        "total": total_records,
        "items": explanations,
        "skip": skip,
        "limit": limit
    }


@router.post("/api/explanations")
def create_explanation(expl: ExplanationCreate, db: Session = Depends(get_db)):
    # --- 1. VALIDATE DATE ---
    today = date.today()
    
    # Điều kiện 1: Ngày truyền lên không được lớn hơn hoặc bằng hôm nay (phải từ hôm qua trở về trước)
    if expl.date >= today:
        raise HTTPException(
            status_code=400, 
            detail="Ngày không hợp lệ! Chỉ có thể giải trình cho các ngày trong quá khứ (đến ngày hôm qua)."
        )
        
    # Điều kiện 2: Ngày truyền lên phải nằm trong tháng và năm hiện tại
    if expl.date.month != today.month or expl.date.year != today.year:
        raise HTTPException(
            status_code=400, 
            detail="Ngày không hợp lệ! Chỉ có thể giải trình cho các vi phạm trong tháng hiện tại."
        )

    # --- 2. XỬ LÝ LƯU DATABASE ---
    try:
        new_explanation = Explanation(**expl.dict())
        db.add(new_explanation)
        db.commit()
        db.refresh(new_explanation)
        
        return {
            "status": "success", 
            "message": "Thêm explanation thành công",
            "data": new_explanation
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Lỗi khi lưu dữ liệu: {str(e)}")


@router.put("/api/explanations/{exp_id}/approve")
def approve_explanation(
    exp_id: int, 
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user) # Đã đổi thành dict
):
    # Ràng buộc quyền: Chỉ Manager và Admin
    user_role = current_user.get("role")
    
    if user_role not in ["manager", "admin"]:
        raise HTTPException(status_code=403, detail="Chỉ quản lý hoặc admin mới có quyền duyệt giải trình")

    try:
        # Lấy bản ghi Explanation
        explanation = db.query(Explanation).filter(Explanation.id == exp_id).first()
        if not explanation:
            raise HTTPException(status_code=404, detail="Không tìm thấy bản ghi giải trình")

        username = explanation.username
        target_date = explanation.date # Kiểu Date

        # Lấy thông tin Employee
        employee = db.query(Employee).filter(Employee.username == username).first()
        if not employee:
            raise HTTPException(status_code=404, detail="Không tìm thấy nhân viên")

        # BƯỚC 1: Lấy shift_code từ ShiftAssignment
        shift_assign = db.query(ShiftAssignment).filter(
            ShiftAssignment.employee_id == employee.id,
            ShiftAssignment.shift_date == target_date
        ).first()
        
        shift_code = shift_assign.shift_code if shift_assign else 'X'

        # BƯỚC 2: Lấy start_time, end_time từ ShiftCategory
        shift_cat = db.query(ShiftCategory).filter(ShiftCategory.shift_code == shift_code).first()
        if not shift_cat:
            raise HTTPException(status_code=400, detail=f"Không tìm thấy cấu hình thời gian cho ca: {shift_code}")

        start_time = shift_cat.start_time
        end_time = shift_cat.end_time

        # Tính toán thời gian Check-in và Check-out mục tiêu
        target_checkin = datetime.combine(target_date, start_time)
        
        # Nếu ca là 'T' (Qua đêm), check-out cộng thêm 1 ngày
        if shift_code == 'T':
            target_checkout = datetime.combine(target_date + timedelta(days=1), end_time)
        else:
            target_checkout = datetime.combine(target_date, end_time)

        # BƯỚC 3: Lấy danh sách Attendance trong ngày
        attendances = db.query(Attendance).filter(
            Attendance.username == username,
            cast(Attendance.check_in_time, Date) == target_date
        ).order_by(Attendance.check_in_time.asc()).all()

        record_count = len(attendances)

        # --- TH1: KHÔNG CÓ BẢN GHI NÀO ---
        if record_count == 0:
            att1 = Attendance(
                username=username,
                full_name=employee.full_name,
                check_in_time=target_checkin,
                explanation_status="APPROVED"
            )
            att2 = Attendance(
                username=username,
                full_name=employee.full_name,
                check_in_time=target_checkout,
                explanation_status="APPROVED"
            )
            db.add_all([att1, att2])

        # --- TH2: CÓ ĐÚNG 1 BẢN GHI ---
        elif record_count == 1:
            att1 = attendances[0]
            att1.check_in_time = target_checkin
            att1.explanation_status = "APPROVED"

            if shift_code == 'T':
                # Tìm bản ghi của ngày hôm sau
                next_day = target_date + timedelta(days=1)
                next_day_atts = db.query(Attendance).filter(
                    Attendance.username == username,
                    cast(Attendance.check_in_time, Date) == next_day
                ).order_by(Attendance.check_in_time.asc()).all()

                if not next_day_atts:
                    # Nếu hôm sau không có, tạo mới
                    att2 = Attendance(
                        username=username,
                        full_name=employee.full_name,
                        check_in_time=target_checkout,
                        explanation_status="APPROVED"
                    )
                    db.add(att2)
                else:
                    # Nếu hôm sau có, update bản ghi đầu tiên của hôm sau
                    att2 = next_day_atts[0]
                    att2.check_in_time = target_checkout
                    att2.explanation_status = "APPROVED"
            else:
                # Không qua đêm thì tạo thêm bản ghi thứ 2 cho ngày hôm đó
                att2 = Attendance(
                    username=username,
                    full_name=employee.full_name,
                    check_in_time=target_checkout,
                    explanation_status="APPROVED"
                )
                db.add(att2)

        # --- TH3: CÓ >= 2 BẢN GHI ---
        else:
            first_att = attendances[0]
            last_att = attendances[-1]

            first_att.check_in_time = target_checkin
            first_att.explanation_status = "APPROVED"

            last_att.check_in_time = target_checkout
            last_att.explanation_status = "APPROVED"

        # Cập nhật trạng thái của chính bản ghi Explanation thành 2 (APPROVED)
        explanation.status = "2"

        db.commit()

        return {
            "status": "success", 
            "message": "Đã duyệt giải trình và đồng bộ lại dữ liệu chấm công thành công"
        }

    except HTTPException as http_exc:
        # Bắt lại lỗi HTTP cố ý throw ra để ném về client, không rollback lỗi này
        raise http_exc
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Lỗi hệ thống khi xử lý: {str(e)}")

@router.put("/api/explanations/{exp_id}/reject")
def reject_explanation(
    exp_id: int, 
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    # Ràng buộc quyền: Chỉ Manager và Admin
    user_role = current_user.get("role")
    if user_role not in ["manager", "admin"]:
        raise HTTPException(status_code=403, detail="Chỉ quản lý hoặc admin mới có quyền thao tác")

    explanation = db.query(Explanation).filter(Explanation.id == exp_id).first()
    if not explanation:
        raise HTTPException(status_code=404, detail="Không tìm thấy bản ghi giải trình")

    # Đổi trạng thái thành 3 (REJECTED)
    explanation.status = "3" 
    db.commit()

    return {"status": "success", "message": "Đã từ chối giải trình"}


@router.put("/api/explanations/{exp_id}")
def update_explanation(
    exp_id: int,
    expl_update: ExplanationUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    # 1. Tìm bản ghi
    explanation = db.query(Explanation).filter(Explanation.id == exp_id).first()
    if not explanation:
        raise HTTPException(status_code=404, detail="Không tìm thấy bản ghi giải trình")

    user_role = current_user.get("role")
    user_name = current_user.get("username")

    # 2. Ràng buộc quyền: Phải là chủ nhân của giải trình, hoặc là admin/manager
    if explanation.username != user_name:
        raise HTTPException(status_code=403, detail="Bạn không có quyền sửa giải trình của người khác")

    # 3. Ràng buộc logic: Chỉ cho phép sửa khi đang Chờ duyệt (status = 1)
    if str(explanation.status) != "1":
        raise HTTPException(status_code=400, detail="Chỉ có thể sửa khi giải trình đang ở trạng thái chờ duyệt")

    # 4. Validate Date (Y hệt như lúc tạo mới)
    from datetime import date
    today = date.today()
    
    if expl_update.date >= today:
        raise HTTPException(
            status_code=400, 
            detail="Ngày không hợp lệ! Chỉ có thể giải trình cho các ngày trong quá khứ (đến ngày hôm qua)."
        )
        
    if expl_update.date.month != today.month or expl_update.date.year != today.year:
        raise HTTPException(
            status_code=400, 
            detail="Ngày không hợp lệ! Chỉ có thể giải trình cho các vi phạm trong tháng hiện tại."
        )

    # 5. Cập nhật và lưu
    try:
        explanation.date = expl_update.date
        explanation.reason = expl_update.reason
        db.commit()
        return {"status": "success", "message": "Cập nhật giải trình thành công"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Lỗi khi cập nhật dữ liệu: {str(e)}")