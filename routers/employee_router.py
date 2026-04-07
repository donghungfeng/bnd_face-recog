import os
from fastapi import UploadFile, File
from fastapi.responses import StreamingResponse
import pandas as pd
import io
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.util import defaultdict
from database import get_db
from models import Employee, OrganizationUnit, EmployeeDepartment
from schemas import EmployeeCreate, PasswordUpdate, ChangeMyPassword, UpdateMyProfile
from config import DB_PATH
from sqlalchemy.orm import aliased
from sqlalchemy import or_
from routers.auth_router import get_current_user
from fastapi import Depends, Query
from sqlalchemy import or_
import os

router = APIRouter()

@router.post("/api/employees")
def create_employee(emp: EmployeeCreate, db: Session = Depends(get_db)):
    db_emp = db.query(Employee).filter(Employee.username == emp.username).first()
    if db_emp:
        raise HTTPException(status_code=400, detail="Mã nhân sự (Username) đã tồn tại")
    
    # Ép kiểu schema thành dict và loại bỏ list departments để không bị lỗi khi insert bảng Employee
    emp_data = emp.dict(exclude={"departments"})
    
    # Sync dob and date_of_birth
    if emp.date_of_birth:
        emp_data['dob'] = emp.date_of_birth
    if emp.dob:
        emp_data['date_of_birth'] = emp.dob
        
    new_emp = Employee(**emp_data)
    db.add(new_emp)
    db.flush() # Đẩy tạm xuống DB để lấy new_emp.id
    
    # Xử lý insert danh sách phòng ban
    if hasattr(emp, 'departments') and emp.departments:
        for dept in emp.departments:
            new_dept = EmployeeDepartment(
                employee_id=new_emp.id,
                department_id=dept.department_id,
                role=dept.role,
                is_primary=dept.is_primary
            )
            db.add(new_dept)
            
    db.commit()
    return {"status": "success", "message": "Thêm nhân sự thành công"}

# Giả sử bạn đã import các thư viện và hàm cần thiết như Depends, get_db, get_current_user...

@router.get("/api/employees")
def get_employees(
    db: Session = Depends(get_db), 
    page: int = 1, 
    size: int = 15,
    search: str = Query(None),
    department_id: int = Query(None),
    current_user: dict = Depends(get_current_user)
):
    current_username = current_user.get("username")

    # ==========================================
    # 1. TÌM THÔNG TIN USER VÀ QUYỀN TỪ DATABASE
    # ==========================================
    me = db.query(Employee).filter(Employee.username == current_username).first()
    if not me:
        return {"items": [], "total": 0, "page": page, "size": size, "total_pages": 0}

    my_departments = db.query(EmployeeDepartment).filter(
        EmployeeDepartment.employee_id == me.id
    ).all()
    
    is_admin = any(dept.role and dept.role.lower() == "admin" for dept in my_departments)

    # KHỞI TẠO QUERY CƠ BẢN (Chỉ query bảng Employee, KHÔNG join phòng ban ở đây để tránh nhân bản dòng)
    query = db.query(Employee)

    # ==========================================
    # 2. ÁP DỤNG PHÂN QUYỀN NẾU KHÔNG PHẢI ADMIN
    # ==========================================
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

        query = query.filter(Employee.username.in_(list(allowed_usernames)))

    # ==========================================
    # 3. LOGIC TÌM KIẾM & LỌC BỔ SUNG
    # ==========================================
    if search:
        query = query.filter(
            or_(
                Employee.full_name.ilike(f"%{search}%"),
                Employee.username.ilike(f"%{search}%")
            )
        )
        
    # Lọc theo department_id lấy từ bảng mới
    if department_id:
        subq_dept = db.query(EmployeeDepartment.employee_id).filter(EmployeeDepartment.department_id == department_id)
        query = query.filter(Employee.id.in_(subq_dept))

    # ==========================================
    # 4. PHÂN TRANG
    # ==========================================
    total = query.count()
    offset = (page - 1) * size
    
    # Lấy ra danh sách nhân viên của trang hiện tại
    employees = query.order_by(Employee.id.desc()).offset(offset).limit(size).all()

    # ==========================================
    # 5. LẤY THÔNG TIN PHÒNG BAN VÀ GHÉP CHUỖI (DẤU PHẨY)
    # ==========================================
    result = []
    if employees:
        emp_ids = [e.id for e in employees]

        Dept = aliased(OrganizationUnit)
        ParentUnit = aliased(OrganizationUnit)

        dept_query = db.query(
            EmployeeDepartment.employee_id,
            EmployeeDepartment.department_id,
            EmployeeDepartment.role, # <--- BỔ SUNG LẤY CỘT ROLE
            Dept.unit_name.label("dept_name"),
            ParentUnit.unit_name.label("parent_name")
        ).join(
            Dept, EmployeeDepartment.department_id == Dept.id
        ).outerjoin(
            ParentUnit, Dept.parent_id == ParentUnit.id
        ).filter(
            EmployeeDepartment.employee_id.in_(emp_ids)
        ).all()

        emp_depts_map = defaultdict(list)
        for row in dept_query:
            emp_depts_map[row.employee_id].append({
                "dept_id": str(row.department_id),
                "role": row.role or "user", # <--- LƯU LẠI ROLE
                "dept_name": row.dept_name or "",
                "parent_name": row.parent_name or ""
            })

        for e in employees:
            depts = emp_depts_map.get(e.id, [])
            
            arr_dept_ids = []
            arr_roles = [] # Mảng chứa role
            arr_ten_don_vi = []
            arr_ten_phong_ban = []
            arr_dept_names = []
            
            seen_dept_ids = set()
            
            for d in depts:
                # Dùng Set để lọc trùng mà vẫn giữ đúng thứ tự (Đảm bảo role và dept_id khớp nhau 1-1)
                if d["dept_id"] not in seen_dept_ids:
                    seen_dept_ids.add(d["dept_id"])
                    arr_dept_ids.append(d["dept_id"])
                    arr_roles.append(d["role"]) # <--- THÊM ROLE VÀO MẢNG
                    arr_dept_names.append(d["dept_name"])
                    
                    if d["parent_name"]:
                        arr_ten_don_vi.append(d["parent_name"])
                        if d["dept_name"]: arr_ten_phong_ban.append(d["dept_name"])
                    else:
                        if d["dept_name"]: arr_ten_don_vi.append(d["dept_name"])

            # Nối chuỗi
            str_dept_ids = ",".join(arr_dept_ids)
            str_roles = ",".join(arr_roles) # <--- CHUỖI ROLE: vd "manager,user"
            
            str_dept_names = ", ".join(list(dict.fromkeys(filter(None, arr_dept_names))))
            str_ten_don_vi = ", ".join(list(dict.fromkeys(filter(None, arr_ten_don_vi))))
            str_ten_phong_ban = ", ".join(list(dict.fromkeys(filter(None, arr_ten_phong_ban))))

            face_path = os.path.join(DB_PATH, f"{e.username}.jpg")

            result.append({
                "id": e.id,
                "username": e.username,
                "full_name": e.full_name,
                "department_id": str_dept_ids, 
                "department_name": str_dept_names,
                "ten_don_vi": str_ten_don_vi,
                "ten_phong_ban": str_ten_phong_ban,
                "phone": e.phone,
                "dob": e.dob,
                "status": e.status,
                "role": str_roles if str_roles else e.role, # <--- TRẢ VỀ ROLE ĐÃ NỐI CHUỖI TỪ BẢNG MỚI
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

from sqlalchemy.orm import aliased
import os

@router.get("/api/employees/me")
def get_current_employee_info(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    current_username = current_user.get("username")

    e = db.query(Employee).filter(Employee.username == current_username).first()
    if not e:
        raise HTTPException(status_code=404, detail="Không tìm thấy thông tin tài khoản hiện tại")

    Dept = aliased(OrganizationUnit)
    ParentUnit = aliased(OrganizationUnit)

    dept_query = db.query(
        EmployeeDepartment.department_id,
        EmployeeDepartment.role, # <--- LẤY CỘT ROLE
        Dept.unit_name.label("dept_name"),
        ParentUnit.unit_name.label("parent_name")
    ).join(
        Dept, EmployeeDepartment.department_id == Dept.id
    ).outerjoin(
        ParentUnit, Dept.parent_id == ParentUnit.id
    ).filter(
        EmployeeDepartment.employee_id == e.id
    ).all()

    arr_dept_ids = []
    arr_roles = [] # <--- KHỞI TẠO MẢNG
    arr_dept_names = []
    arr_ten_don_vi = []
    arr_ten_phong_ban = []

    seen_dept_ids = set()

    for row in dept_query:
        if str(row.department_id) not in seen_dept_ids:
            seen_dept_ids.add(str(row.department_id))
            arr_dept_ids.append(str(row.department_id))
            arr_roles.append(row.role or "user") # <--- THÊM ROLE
            arr_dept_names.append(row.dept_name or "")
            
            if row.parent_name:
                arr_ten_don_vi.append(row.parent_name)
                if row.dept_name: arr_ten_phong_ban.append(row.dept_name)
            else:
                if row.dept_name: arr_ten_don_vi.append(row.dept_name)

    str_dept_ids = ",".join(arr_dept_ids)
    str_roles = ",".join(arr_roles) # <--- NỐI CHUỖI ROLE
    
    str_dept_names = ", ".join(list(dict.fromkeys(filter(None, arr_dept_names))))
    str_ten_don_vi = ", ".join(list(dict.fromkeys(filter(None, arr_ten_don_vi))))
    str_ten_phong_ban = ", ".join(list(dict.fromkeys(filter(None, arr_ten_phong_ban))))

    face_path = os.path.join(DB_PATH, f"{e.username}.jpg")

    return {
        "status": "success",
        "data": {
            "id": e.id,
            "username": e.username,
            "full_name": e.full_name,
            "department_id": str_dept_ids,
            "department_name": str_dept_names,
            "ten_don_vi": str_ten_don_vi,
            "ten_phong_ban": str_ten_phong_ban,
            "phone": e.phone,
            "email": e.email,
            "dob": e.dob, 
            "date_of_birth": e.date_of_birth,
            "status": e.status,
            "role": str_roles if str_roles else e.role, # <--- TRẢ VỀ ROLE ĐÚNG
            "is_locked": e.is_locked,
            "ccCaNhan": e.ccCaNhan,
            "ccTapTrung": e.ccTapTrung,
            "checkViTri": e.checkViTri,
            "checkMang": e.checkMang,
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


@router.get("/api/employees/managers")
def get_managers(db: Session = Depends(get_db)):
    # Join 2 bảng và filter theo role trong bảng EmployeeDepartment
    managers_query = db.query(
        Employee.username, 
        Employee.full_name, 
        EmployeeDepartment.department_id
    ).join(
        EmployeeDepartment, Employee.id == EmployeeDepartment.employee_id
    ).filter(
        EmployeeDepartment.role.in_(["manager", "admin"]), 
        Employee.status == "active"
    ).all()
    
    # Dùng list comprehension để map dữ liệu
    return [
        {
            "username": m.username,
            "full_name": m.full_name,
            "department_id": m.department_id
        }
        for m in managers_query
    ]

@router.put("/api/employees/{username}")
def update_employee(username: str, emp: EmployeeCreate, db: Session = Depends(get_db)):
    db_emp = db.query(Employee).filter(Employee.username == username).first()
    if not db_emp:
        raise HTTPException(status_code=404, detail="Không tìm thấy nhân sự")
    
    # 1. CẬP NHẬT THÔNG TIN CƠ BẢN
    db_emp.full_name = emp.full_name
    db_emp.phone = emp.phone
    db_emp.email = emp.email
    
    # Sync dob and date_of_birth
    target_dob = emp.date_of_birth or emp.dob
    db_emp.date_of_birth = target_dob
    db_emp.dob = target_dob
    
    db_emp.status = emp.status
    db_emp.is_locked = emp.is_locked
    db_emp.notes = emp.notes
    db_emp.ccCaNhan = emp.ccCaNhan
    db_emp.ccTapTrung = emp.ccTapTrung
    db_emp.checkViTri = emp.checkViTri
    db_emp.checkMang = emp.checkMang
    db_emp.hourly_rate = emp.hourly_rate
    db_emp.allowance = emp.allowance
    
    # Cập nhật username (Lưu ý: Nếu đổi username, cẩn thận ảnh hưởng đến các bảng dùng username làm khóa phụ như Attendance)
    db_emp.username = emp.username 

    # 2. XỬ LÝ DANH SÁCH PHÒNG BAN & QUYỀN
    if emp.departments is not None:
        # Xóa toàn bộ phòng ban và quyền cũ của nhân viên này
        db.query(EmployeeDepartment).filter(EmployeeDepartment.employee_id == db_emp.id).delete()
        
        # Thêm danh sách phòng ban mới
        for dept in emp.departments:
            new_dept = EmployeeDepartment(
                employee_id=db_emp.id,
                department_id=dept.department_id,
                role=dept.role,
                is_primary=dept.is_primary
            )
            db.add(new_dept)
            
    # Đồng bộ lưu trữ xuống database
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

    # 1. QUYỀN HẠN TỪ BẢNG MỚI
    me = db.query(Employee).filter(Employee.username == current_username).first()
    if not me:
        return {"status": "success", "items": [], "total": 0}

    my_departments = db.query(EmployeeDepartment).filter(
        EmployeeDepartment.employee_id == me.id
    ).all()
    is_admin = any(dept.role and dept.role.lower() == "admin" for dept in my_departments)

    query = db.query(Employee)

    # 2. PHÂN QUYỀN: MANAGER CHỈ THẤY NHÂN VIÊN TRONG PHÒNG
    if not is_admin:
        allowed_usernames = {current_username}
        managed_dept_ids = [d.department_id for d in my_departments if d.role and d.role.lower() == "manager"]

        if managed_dept_ids:
            dept_users = db.query(Employee.username).join(EmployeeDepartment).filter(
                EmployeeDepartment.department_id.in_(managed_dept_ids)
            ).all()
            for u in dept_users: allowed_usernames.add(u[0])

        query = query.filter(Employee.username.in_(list(allowed_usernames)))

    # 3. LẤY DỮ LIỆU
    employees = query.order_by(Employee.id.desc()).all()

    # 4. MAP PHÒNG BAN VÀ TRẢ VỀ CHUỖI
    result = []
    if employees:
        emp_ids = [e.id for e in employees]
        Dept = aliased(OrganizationUnit)
        ParentUnit = aliased(OrganizationUnit)

        dept_query = db.query(
            EmployeeDepartment.employee_id,
            EmployeeDepartment.department_id,
            EmployeeDepartment.role,
            Dept.unit_name.label("dept_name"),
            ParentUnit.unit_name.label("parent_name")
        ).join(Dept, EmployeeDepartment.department_id == Dept.id)\
         .outerjoin(ParentUnit, Dept.parent_id == ParentUnit.id)\
         .filter(EmployeeDepartment.employee_id.in_(emp_ids)).all()

        emp_depts_map = defaultdict(list)
        for row in dept_query:
            emp_depts_map[row.employee_id].append(row)

        for e in employees:
            depts = emp_depts_map.get(e.id, [])
            
            arr_dept_ids = [str(d.department_id) for d in depts]
            arr_roles = [d.role for d in depts if d.role]
            arr_dept_names = [d.dept_name for d in depts if d.dept_name]
            
            arr_ten_don_vi = []
            arr_ten_phong_ban = []
            for d in depts:
                if d.parent_name:
                    arr_ten_don_vi.append(d.parent_name)
                    if d.dept_name: arr_ten_phong_ban.append(d.dept_name)
                elif d.dept_name:
                    arr_ten_don_vi.append(d.dept_name)

            result.append({
                "id": e.id,
                "username": e.username,
                "full_name": e.full_name,
                "department_id": ",".join(list(dict.fromkeys(arr_dept_ids))),
                "department_name": ", ".join(list(dict.fromkeys(arr_dept_names))),
                "ten_don_vi": ", ".join(list(dict.fromkeys(arr_ten_don_vi))),
                "ten_phong_ban": ", ".join(list(dict.fromkeys(arr_ten_phong_ban))),
                "phone": e.phone,
                "dob": e.dob,
                "status": e.status,
                "role": ", ".join(list(dict.fromkeys(arr_roles))) if arr_roles else e.role,
                "is_locked": e.is_locked,
                "date_of_birth": e.date_of_birth,
                "ccCaNhan": e.ccCaNhan,
                "ccTapTrung": e.ccTapTrung,
                "checkViTri": e.checkViTri,
                "checkMang": e.checkMang,
                "email": getattr(e, "email", "")
            })

    return {
        "status": "success",
        "items": result,
        "total": len(result)
    }