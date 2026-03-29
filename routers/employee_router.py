import os
from fastapi import UploadFile, File
from fastapi.responses import StreamingResponse
import pandas as pd
import io
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from database import get_db
from models import Employee, OrganizationUnit
from schemas import EmployeeCreate, PasswordUpdate, ChangeMyPassword, UpdateMyProfile
from config import DB_PATH
from sqlalchemy.orm import aliased
from sqlalchemy import or_
from routers.auth_router import get_current_user

router = APIRouter()

@router.post("/api/employees")
def create_employee(emp: EmployeeCreate, db: Session = Depends(get_db)):
    db_emp = db.query(Employee).filter(Employee.username == emp.username).first()
    if db_emp:
        raise HTTPException(status_code=400, detail="Mã nhân sự (Username) đã tồn tại")
    
    emp_data = emp.dict()
    # Sync dob and date_of_birth
    if emp.date_of_birth:
        emp_data['dob'] = emp.date_of_birth
    if emp.dob:
        emp_data['date_of_birth'] = emp.dob
        
    new_emp = Employee(**emp_data)
    db.add(new_emp)
    db.commit()
    return {"status": "success", "message": "Thêm nhân sự thành công"}

from fastapi import Depends, Query
from sqlalchemy import or_
import os

# Giả sử bạn đã import các thư viện và hàm cần thiết như Depends, get_db, get_current_user...

@router.get("/api/employees")
def get_employees(
    db: Session = Depends(get_db), 
    page: int = 1, 
    size: int = 15,
    search: str = Query(None),
    department_id: int = Query(None),
    current_user: dict = Depends(get_current_user)  # <-- Bổ sung dependency lấy user hiện tại
):
    current_username = current_user.get("username")
    current_role = current_user.get("role", "user")

    Dept = aliased(OrganizationUnit)
    ParentUnit = aliased(OrganizationUnit)

    query = db.query(
        Employee,
        Dept.unit_name.label("dept_name"),
        ParentUnit.unit_name.label("parent_name")
    ).outerjoin(
        Dept, Employee.department_id == Dept.id
    ).outerjoin(
        ParentUnit, Dept.parent_id == ParentUnit.id
    )

    # ==========================================
    # LOGIC PHÂN QUYỀN (RBAC)
    # ==========================================
    if current_role == "admin":
        # Admin được xem tất cả -> Không cần filter thêm
        pass
        
    elif current_role == "manager":
        # Lấy ID phòng ban của chính manager này
        manager_dept_id = db.query(Employee.department_id).filter(Employee.username == current_username).scalar()
        
        if manager_dept_id:
            # Manager chỉ được xem nhân viên trong cùng phòng ban
            query = query.filter(Employee.department_id == manager_dept_id)
        else:
            # Fallback an toàn: Nếu manager chưa được xếp phòng, chỉ cho xem chính họ
            query = query.filter(Employee.username == current_username)
            
    else:
        # Role 'user' hoặc các role không xác định khác: Chỉ xem được chính mình
        query = query.filter(Employee.username == current_username)

    # ==========================================
    # LOGIC TÌM KIẾM & LỌC BỔ SUNG
    # ==========================================
    if search:
        query = query.filter(
            or_(
                Employee.full_name.ilike(f"%{search}%"),
                Employee.username.ilike(f"%{search}%")
            )
        )
        
    # Lọc theo department_id (từ frontend gửi lên)
    # Lưu ý: Nếu là Manager, điều kiện này sẽ kết hợp (AND) với điều kiện RBAC ở trên. 
    # Nếu Manager cố tình chọn phòng ban khác, query sẽ tự động trả về rỗng -> Rất bảo mật!
    if department_id:
        query = query.filter(Employee.department_id == department_id)

    # ==========================================
    # PHÂN TRANG & MAP KẾT QUẢ
    # ==========================================
    total = query.count()
    offset = (page - 1) * size

    rows = query.order_by(Employee.id.desc()).offset(offset).limit(size).all()

    result = []
    for e, dept_name, parent_name in rows:
        face_path = os.path.join(DB_PATH, f"{e.username}.jpg")

        if parent_name:
            ten_don_vi = parent_name
            ten_phong_ban = dept_name or ""
        else:
            ten_don_vi = dept_name or ""
            ten_phong_ban = ""

        result.append({
            "id": e.id,
            "username": e.username,
            "full_name": e.full_name,
            "department_id": e.department_id,
            "department_name": dept_name,
            "ten_don_vi": ten_don_vi,
            "ten_phong_ban": ten_phong_ban,
            "phone": e.phone,
            "dob": e.dob,
            "status": e.status,
            "role": e.role,
            "is_locked": e.is_locked,
            "date_of_birth": e.date_of_birth,
            "ccCaNhan": e.ccCaNhan,
            "ccTapTrung": e.ccTapTrung,
            "checkViTri": e.checkViTri,
            "checkMang": e.checkMang,
            "has_face": os.path.exists(face_path)
        })
    
    return {
        "items": result,
        "total": total,
        "page": page,
        "size": size,
        "total_pages": (total + size - 1) // size if size > 0 else 1
    }

@router.put("/api/employees/me")
def update_my_profile(
    req: UpdateMyProfile,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    current_username = current_user.get("username")
    db_emp = db.query(Employee).filter(Employee.username == current_username).first()
    if not db_emp:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản")

    db_emp.full_name = req.full_name
    db_emp.phone     = req.phone
    db_emp.email     = req.email
    
    # Sync dob and date_of_birth
    db_emp.dob = req.dob
    db_emp.date_of_birth = req.date_of_birth

    db_emp.notes     = req.notes
    db_emp.ccCaNhan  = req.ccCaNhan
    db_emp.ccTapTrung = req.ccTapTrung
    db.commit()
    db.refresh(db_emp)

    face_path = os.path.join(DB_PATH, f"{db_emp.username}.jpg")
    return {
        "status": "success",
        "message": "Cập nhật thông tin thành công!",
        "data": {
            "id": db_emp.id,
            "username": db_emp.username,
            "full_name": db_emp.full_name,
            "phone": db_emp.phone,
            "email": db_emp.email,
            "dob": db_emp.dob,
            "date_of_birth": db_emp.date_of_birth,
            "notes": db_emp.notes,
            "role": db_emp.role,
            "status": db_emp.status,
            "department_id": db_emp.department_id,
            "is_locked": db_emp.is_locked,
            "ccCaNhan": db_emp.ccCaNhan,
            "ccTapTrung": db_emp.ccTapTrung,
            "checkViTri": db_emp.checkViTri,
            "checkMang": db_emp.checkMang,
            "has_face": os.path.exists(face_path)
        }
    }
    
@router.post("/api/employees/auto-update-departments")
def auto_update_departments(db: Session = Depends(get_db)):
    # 1. Query tất cả employee có department_id là null
    employees_no_dept = db.query(Employee).all()
    
    if not employees_no_dept:
        return {"message": "Không có nhân viên nào cần cập nhật phòng ban.", "updated_count": 0}

    # 2. Group các employee theo công thức username.split(".")[0]
    # Map sẽ có dạng: {"A": [emp1, emp2], "B": [emp3]}
    grouped_employees = {}
    for emp in employees_no_dept:
        if not emp.username:
            continue
            
        prefix = emp.username.split(".")[0] # Lấy phần tử đầu tiên, VD: A.B -> A
        
        if prefix not in grouped_employees:
            grouped_employees[prefix] = []
        grouped_employees[prefix].append(emp)

    result = []
    updated_count = 0

    # 3. Duyệt qua map để query và update
    for prefix, emp_list in grouped_employees.items():
        # Query xuống bảng organization_units filter theo unit_code
        org_unit = db.query(OrganizationUnit).filter(OrganizationUnit.unit_code == prefix).first()
        
        # Nếu tìm thấy đơn vị (phòng ban) có mã tương ứng
        if org_unit:
            org_unit_id = org_unit.id
            
            # Lấy hết value theo key của map và update department_id
            for emp in emp_list:
                emp.department_id = org_unit_id
                result.append(emp.username) # Thêm vào list result (ở đây mình lấy username để trả về cho dễ nhìn)
                updated_count += 1

    # 4. Update chúng xuống DB (Commit toàn bộ thay đổi cùng 1 lúc)
    if updated_count > 0:
        db.commit()

    return {
        "message": "Cập nhật phòng ban tự động thành công!",
        "updated_count": updated_count,
        "updated_usernames": result
    }

@router.put("/api/employees/{username}")
def update_employee(username: str, emp: EmployeeCreate, db: Session = Depends(get_db)):
    db_emp = db.query(Employee).filter(Employee.username == username).first()
    if not db_emp:
        raise HTTPException(status_code=404, detail="Không tìm thấy nhân sự")
    
    db_emp.full_name = emp.full_name
    db_emp.phone = emp.phone
    db_emp.email = emp.email
    
    # Sync dob and date_of_birth
    target_dob = emp.date_of_birth or emp.dob
    db_emp.date_of_birth = target_dob
    db_emp.dob = target_dob
    
    db_emp.department_id = emp.department_id
    db_emp.status = emp.status
    db_emp.role = emp.role
    db_emp.is_locked = emp.is_locked
    db_emp.notes = emp.notes
    db_emp.ccCaNhan = emp.ccCaNhan
    db_emp.ccTapTrung = emp.ccTapTrung
    db_emp.checkViTri = emp.checkViTri
    db_emp.checkMang = emp.checkMang
    db_emp.hourly_rate = emp.hourly_rate
    db_emp.allowance = emp.allowance
    db_emp.username = emp.username # CẬP NHẬT THEO USERNAME MỚI (nếu có thay đổi)

    db.commit()
    return {"status": "success", "message": "Đã cập nhật thông tin"}

@router.delete("/api/employees/{username}")
def delete_employee(username: str, db: Session = Depends(get_db)):
    db_emp = db.query(Employee).filter(Employee.username == username).first()
    if not db_emp:
        raise HTTPException(status_code=404, detail="Không tìm thấy nhân sự")
    db.delete(db_emp)
    db.commit()
    return {"status": "success"}

# --- API MỚI: ĐỔI MẬT KHẨU ---
@router.put("/api/employees/{username}/password")
def update_password(username: str, req: PasswordUpdate, db: Session = Depends(get_db)):
    db_emp = db.query(Employee).filter(Employee.username == username).first()
    if not db_emp:
        raise HTTPException(status_code=404, detail="Không tìm thấy nhân sự")
    
    db_emp.password = req.new_password
    db.commit()
    return {"status": "success", "message": "Đã đổi mật khẩu thành công!"}

# --- API MỚI: KHÓA / MỞ KHÓA TÀI KHOẢN ---
@router.put("/api/employees/{username}/toggle_lock")
def toggle_account_lock(username: str, db: Session = Depends(get_db)):
    db_emp = db.query(Employee).filter(Employee.username == username).first()
    if not db_emp:
        raise HTTPException(status_code=404, detail="Không tìm thấy nhân sự")
    
    # Đảo ngược trạng thái khóa (0 thành 1, 1 thành 0)
    db_emp.is_locked = 1 if db_emp.is_locked == 0 else 0
    db.commit()
    
    status_str = "khóa" if db_emp.is_locked == 1 else "mở khóa"
    return {"status": "success", "message": f"Tài khoản {username} đã được {status_str}."}

# ==========================================
# 1. API XUẤT EXCEL
# ==========================================
@router.get("/api/employees/export")
def export_employees(db: Session = Depends(get_db)):
    emps = db.query(Employee).all()
    
    # Tạo danh sách dữ liệu
    data = []
    for e in emps:
        data.append({
            "Mã NV (Username)": e.username,
            "Họ và Tên": e.full_name,
            "Ngày Sinh": e.date_of_birth.strftime("%Y-%m-%d") if e.date_of_birth else "",
            "Phòng Ban ID": e.department_id,
            "Chức vụ (Role)": e.role,
            "Trạng thái": e.status
        })
        
    df = pd.DataFrame(data)
    
    # Ghi ra file Excel ảo trên RAM (không cần lưu xuống ổ cứng)
    stream = io.BytesIO()
    with pd.ExcelWriter(stream, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name="NhanSu")
    stream.seek(0)
    
    # Cấu hình trả file về trình duyệt
    headers = {
        'Content-Disposition': 'attachment; filename="DanhSachNhanSu.xlsx"'
    }
    return StreamingResponse(stream, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers=headers)

# ==========================================
# 2. API NHẬP EXCEL
# ==========================================
@router.post("/api/employees/import")
async def import_employees(file: UploadFile = File(...), db: Session = Depends(get_db)):
    import pandas as pd
    import io
    from fastapi import HTTPException
    
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="Vui lòng tải lên file Excel (.xlsx)")
        
    try:
        contents = await file.read()
        df = pd.read_excel(io.BytesIO(contents))
        
        # BỎ df.fillna("") ĐỂ KHÔNG LÀM HỎNG ĐỊNH DẠNG NGÀY THÁNG CỦA EXCEL
        
        success_count = 0
        for index, row in df.iterrows():
            # Lấy Mã NV
            username_raw = row.get("Mã NV (Username)")
            # pd.isna() giúp kiểm tra ô đó có bị trống không một cách an toàn
            if pd.isna(username_raw) or str(username_raw).strip() == "":
                continue 
            username = str(username_raw).strip().upper()
                
            # Lấy Họ Tên
            full_name_raw = row.get("Họ và Tên")
            full_name = str(full_name_raw).strip() if pd.notna(full_name_raw) else ""
            
            # 1. XỬ LÝ NGÀY SINH (ĐÃ SỬA LỖI ĐỊNH DẠNG)
            dob_raw = row.get("Ngày Sinh")
            dob = None
            if pd.notna(dob_raw) and str(dob_raw).strip() != "":
                try:
                    # errors='coerce' sẽ tự động trả về NaT (Not a Time) nếu dữ liệu bị lỗi, không làm sập App
                    parsed_date = pd.to_datetime(dob_raw, errors='coerce')
                    if pd.notna(parsed_date): 
                        dob = parsed_date.date() # Lấy đúng phần Ngày (Bỏ qua Giờ Phút)
                except:
                    pass
            
            # 2. XỬ LÝ PHÒNG BAN ID
            dept_id_raw = row.get("Phòng Ban ID")
            dept_id = None
            if pd.notna(dept_id_raw) and str(dept_id_raw).strip() != "":
                try:
                    dept_id = int(float(dept_id_raw))
                except ValueError:
                    dept_id = None
            
            # 3. XỬ LÝ QUYỀN VÀ TRẠNG THÁI
            role_raw = row.get("Chức vụ (Role)")
            role_val = str(role_raw).strip().lower() if pd.notna(role_raw) else "user"
            if role_val not in ["admin", "manager", "user"]: role_val = "user"
            
            status_raw = row.get("Trạng thái")
            status_val = str(status_raw).strip().lower() if pd.notna(status_raw) else "active"
            if status_val not in ["active", "inactive"]: status_val = "active"
            
            # Kiểm tra và lưu vào DB
            exist = db.query(Employee).filter(Employee.username == username).first()
            if not exist:
                new_emp = Employee(
                    username=username,
                    full_name=full_name,
                    date_of_birth=dob,
                    dob=dob, # Sync
                    department_id=dept_id,
                    password="123456",           
                    role=role_val,            
                    status=status_val,        
                    is_locked=0
                )
                db.add(new_emp)
                success_count += 1
                
        db.commit()
        return {"status": "success", "message": f"Đã nhập thành công {success_count} nhân viên mới!"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi đọc file Excel: {str(e)}")

@router.get("/api/employees/export_template")
def export_template(db: Session = Depends(get_db)):
    
    # --- SHEET 1: MẪU ĐIỀN NHÂN SỰ ---
    data_emp = [{
        "Mã NV (Username)": "NV001",
        "Họ và Tên": "Nguyễn Văn A",
        "Ngày Sinh": "1995-10-25",
        "Phòng Ban ID": "1", # Gợi ý điền ID
        "Chức vụ (Role)": "user",
        "Trạng thái": "active"
    }]
    df_emp = pd.DataFrame(data_emp)
    
    # --- SHEET 2: DANH SÁCH PHÒNG BAN THAM CHIẾU ---
    depts = db.query(OrganizationUnit).all()
    data_dept = []
    for d in depts:
        data_dept.append({
            "ID (Điền vào cột Phòng Ban ID)": d.id,
            "Mã Đơn Vị": d.unit_code,
            "Tên Phòng Ban": d.unit_name
        })
        
    # Nếu hệ thống của bạn chưa tạo phòng ban nào, tạo 1 dòng ảo để làm mẫu
    if not data_dept:
        data_dept = [{
            "ID (Điền vào cột Phòng Ban ID)": "---",
            "Mã Đơn Vị": "---",
            "Tên Phòng Ban": "Hệ thống chưa có phòng ban nào. Hãy tạo trên Web trước!"
        }]
        
    df_dept = pd.DataFrame(data_dept)
    
    # --- XUẤT RA FILE EXCEL VỚI 2 SHEET ---
    stream = io.BytesIO()
    with pd.ExcelWriter(stream, engine='openpyxl') as writer:
        df_emp.to_excel(writer, index=False, sheet_name="NhanSu")
        df_dept.to_excel(writer, index=False, sheet_name="MaPhongBan")
        
        # Tự động điều chỉnh độ rộng cột cho Sheet Mã Phòng Ban dễ nhìn
        worksheet = writer.sheets['MaPhongBan']
        worksheet.column_dimensions['A'].width = 35
        worksheet.column_dimensions['B'].width = 15
        worksheet.column_dimensions['C'].width = 40

    stream.seek(0)
    
    headers = {'Content-Disposition': 'attachment; filename="FileMau_NhapNhanSu.xlsx"'}
    return StreamingResponse(stream, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers=headers)


# Giả sử bạn có một hàm get_current_user để lấy username từ Token
# from auth_dependencies import get_current_user 

@router.get("/api/employees/me")
def get_current_employee_info(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)  # trả về dict: {'username':..., 'role':...}
):
    current_username = current_user.get("username")

    Dept = aliased(OrganizationUnit)
    ParentUnit = aliased(OrganizationUnit)

    # Query thông tin của user kèm theo tên phòng ban/đơn vị
    result = db.query(
        Employee,
        Dept.unit_name.label("dept_name"),
        ParentUnit.unit_name.label("parent_name")
    ).outerjoin(
        Dept, Employee.department_id == Dept.id
    ).outerjoin(
        ParentUnit, Dept.parent_id == ParentUnit.id
    ).filter(Employee.username == current_username).first()

    if not result:
        raise HTTPException(status_code=404, detail="Không tìm thấy thông tin tài khoản hiện tại")

    e, dept_name, parent_name = result
    
    # Kiểm tra ảnh khuôn mặt
    face_path = os.path.join(DB_PATH, f"{e.username}.jpg")

    # Xử lý logic tên đơn vị / phòng ban
    if parent_name:
        ten_don_vi = parent_name
        ten_phong_ban = dept_name or ""
    else:
        ten_don_vi = dept_name or ""
        ten_phong_ban = ""

    # Trả về chi tiết bản ghi
    return {
        "status": "success",
        "data": {
            "id": e.id,
            "username": e.username,
            "full_name": e.full_name,
            "department_id": e.department_id,
            "department_name": dept_name,
            "ten_don_vi": ten_don_vi,
            "ten_phong_ban": ten_phong_ban,
            "phone": e.phone,
            "dob": e.dob, # Đảm bảo field này trùng khớp với model của bạn (dob hay date_of_birth)
            "status": e.status,
            "role": e.role,
            "is_locked": e.is_locked,
            "date_of_birth": e.date_of_birth,
            "ccCaNhan": e.ccCaNhan,
            "ccTapTrung": e.ccTapTrung,
            "checkViTri": e.checkViTri,
            "checkMang": e.checkMang,
            "has_face": os.path.exists(face_path),
            "email": e.email,
        }
    }

@router.put("/api/employees/me/password")
def change_my_password(
    req: ChangeMyPassword,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)  # trả về dict
):
    current_username = current_user.get("username")
    db_emp = db.query(Employee).filter(Employee.username == current_username).first()
    if not db_emp:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản")
    
    # Xác minh mật khẩu cũ
    # Lưu ý: Dựa theo code của bạn, mật khẩu đang được lưu dưới dạng plain-text (chữ thường).
    if db_emp.password != req.old_password:
        raise HTTPException(status_code=400, detail="Mật khẩu cũ không chính xác")
    
    # Tránh trường hợp mật khẩu mới giống mật khẩu cũ
    if req.old_password == req.new_password:
        raise HTTPException(status_code=400, detail="Mật khẩu mới phải khác mật khẩu hiện tại")
    
    # Cập nhật mật khẩu mới
    db_emp.password = req.new_password
    db.commit()
    
    return {"status": "success", "message": "Đổi mật khẩu thành công!"}

@router.get("/api/employees/accessible")
def get_accessible_employees(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    current_username = current_user.get("username")
    current_role = current_user.get("role")

    # 1. Lấy nhanh thông tin phòng ban của user hiện tại
    # Chỉ lấy đúng giá trị (scalar), không lấy cả object Employee
    current_dept_id = db.query(Employee.department_id).filter(Employee.username == current_username).scalar()

    # 2. Định nghĩa danh sách các cột cần lấy (Đầy đủ như bạn muốn)
    # Liệt kê cụ thể giúp DB tối ưu hóa tốc độ truy xuất hơn là dùng SELECT *
    target_columns = [
        Employee.id, Employee.username, Employee.full_name, 
        Employee.department_id, Employee.phone, Employee.dob, 
        Employee.status, Employee.role, Employee.is_locked, 
        Employee.date_of_birth, Employee.ccCaNhan, Employee.ccTapTrung,
        Employee.checkViTri, Employee.checkMang
    ]
    
    # Kiểm tra nếu model có email thì lấy luôn
    if hasattr(Employee, 'email'):
        target_columns.append(Employee.email)

    Dept = aliased(OrganizationUnit)
    ParentUnit = aliased(OrganizationUnit)

    # 3. Xây dựng Query tập trung vào tốc độ
    query = db.query(
        *target_columns,
        Dept.unit_name.label("dept_name"),
        ParentUnit.unit_name.label("parent_name")
    ).outerjoin(
        Dept, Employee.department_id == Dept.id
    ).outerjoin(
        ParentUnit, Dept.parent_id == ParentUnit.id
    )

    # 4. Phân quyền
    if current_role == "manager" and current_dept_id:
        query = query.filter(Employee.department_id == current_dept_id)
    elif current_role != "admin":
        query = query.filter(Employee.username == current_username)

    # 5. Lấy dữ liệu dạng Row (Tốc độ cao hơn lấy dạng Object)
    rows = query.order_by(Employee.id.desc()).all()

    # 6. Dùng List Comprehension (Cách nhanh nhất trong Python để tạo List)
    return {
        "status": "success",
        "items": [
            {
                "id": r.id,
                "username": r.username,
                "full_name": r.full_name,
                "department_id": r.department_id,
                "department_name": r.dept_name or "",
                "ten_don_vi": r.parent_name if r.parent_name else (r.dept_name or ""),
                "ten_phong_ban": r.dept_name if r.parent_name else "",
                "phone": r.phone,
                "dob": r.dob,
                "status": r.status,
                "role": r.role,
                "is_locked": r.is_locked,
                "date_of_birth": r.date_of_birth,
                "ccCaNhan": r.ccCaNhan,
                "ccTapTrung": r.ccTapTrung,
                "checkViTri": r.checkViTri,
                "checkMang": r.checkMang,
                "email": getattr(r, "email", "")
            }
            for r in rows
        ],
        "total": len(rows)
    }