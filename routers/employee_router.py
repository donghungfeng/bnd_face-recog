import os
from fastapi import UploadFile, File
from fastapi.responses import StreamingResponse
import pandas as pd
import io
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from database import get_db
from models import Employee, OrganizationUnit
from schemas import EmployeeCreate, PasswordUpdate
from config import DB_PATH
from sqlalchemy.orm import aliased
from sqlalchemy import or_

router = APIRouter()

@router.post("/api/employees")
def create_employee(emp: EmployeeCreate, db: Session = Depends(get_db)):
    db_emp = db.query(Employee).filter(Employee.username == emp.username).first()
    if db_emp:
        raise HTTPException(status_code=400, detail="Mã nhân sự (Username) đã tồn tại")
    
    new_emp = Employee(**emp.dict())
    db.add(new_emp)
    db.commit()
    return {"status": "success", "message": "Thêm nhân sự thành công"}

@router.get("/api/employees")
def get_employees(
    db: Session = Depends(get_db), 
    page: int = 1, 
    size: int = 15,
    search: str = Query(None),
    department_id: int = Query(None)
):
    
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

    if search:
        query = query.filter(
            or_(
                Employee.full_name.ilike(f"%{search}%"),
                Employee.username.ilike(f"%{search}%")
            )
        )
    if department_id:
        query = query.filter(Employee.department_id == department_id)

    # Lấy tổng số nhân viên (đã lọc) để tính phân trang
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
            "has_face": os.path.exists(face_path)
        })
    
    return {
        "items": result,
        "total": total,
        "page": page,
        "size": size,
        "total_pages": (total + size - 1) // size if size > 0 else 1
    }

@router.put("/api/employees/{username}")
def update_employee(username: str, emp: EmployeeCreate, db: Session = Depends(get_db)):
    db_emp = db.query(Employee).filter(Employee.username == username).first()
    if not db_emp:
        raise HTTPException(status_code=404, detail="Không tìm thấy nhân sự")
    
    db_emp.full_name = emp.full_name
    db_emp.phone = emp.phone
    db_emp.department_id = emp.department_id # CẬP NHẬT THEO ID
    db_emp.status = emp.status
    db_emp.role = emp.role
    db_emp.is_locked = emp.is_locked
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
                    date_of_birth=dob,        # <--- NGÀY SINH ĐÃ ĐƯỢC MAP CHUẨN XÁC
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
    import pandas as pd
    import io
    from fastapi.responses import StreamingResponse
    
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