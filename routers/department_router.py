from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from database import get_db
from models import OrganizationUnit
from schemas import OrgUnitCreate

from fastapi.templating import Jinja2Templates
templates = Jinja2Templates(directory="templates")

router = APIRouter()
@router.get("/departments")

def read_departments(request: Request): 
    return templates.TemplateResponse("departments.html", {"request": request})

@router.post("/api/departments")
def create_department(dept: OrgUnitCreate, db: Session = Depends(get_db)):
    db_dept = db.query(OrganizationUnit).filter(OrganizationUnit.unit_code == dept.unit_code).first()
    if db_dept:
        raise HTTPException(status_code=400, detail="Mã đơn vị đã tồn tại")
    
    new_dept = OrganizationUnit(**dept.dict())
    db.add(new_dept)
    db.commit()
    return {"status": "success", "message": "Thêm đơn vị thành công"}
    

@router.get("/api/departments")
def get_departments(db: Session = Depends(get_db)):
    # Lấy toàn bộ đơn vị và sắp xếp theo số thứ tự để lúc dựng Cây không bị lộn xộn
    return db.query(OrganizationUnit).order_by(OrganizationUnit.order_num.asc()).all()

# THÊM API CẬP NHẬT (SỬA) ĐƠN VỊ
@router.put("/api/departments/{dept_id}")
def update_department(dept_id: int, dept: OrgUnitCreate, db: Session = Depends(get_db)):
    db_dept = db.query(OrganizationUnit).filter(OrganizationUnit.id == dept_id).first()
    if not db_dept:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn vị")
    
    # Kiểm tra nếu đổi mã đơn vị sang một mã khác đã tồn tại
    if db_dept.unit_code != dept.unit_code:
        existing_code = db.query(OrganizationUnit).filter(OrganizationUnit.unit_code == dept.unit_code).first()
        if existing_code:
            raise HTTPException(status_code=400, detail="Mã đơn vị này đã được sử dụng")
            
    # Chống lỗi logic: Đơn vị cha không thể là chính nó
    if dept.parent_id == dept_id:
        raise HTTPException(status_code=400, detail="Đơn vị cha không thể là chính nó")

    # Cập nhật dữ liệu
    db_dept.unit_code = dept.unit_code
    db_dept.unit_name = dept.unit_name
    db_dept.unit_type = dept.unit_type
    db_dept.parent_id = dept.parent_id
    db_dept.order_num = dept.order_num
    db_dept.level = dept.level
    db_dept.location = dept.location
    db_dept.status = dept.status
    db_dept.notes = dept.notes

    db.commit()
    return {"status": "success", "message": "Cập nhật thành công"}

@router.delete("/api/departments/{dept_id}")
def delete_department(dept_id: int, db: Session = Depends(get_db)):
    dept = db.query(OrganizationUnit).filter(OrganizationUnit.id == dept_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn vị")
    
    # Kiểm tra xem có đơn vị con nào đang trực thuộc không
    children = db.query(OrganizationUnit).filter(OrganizationUnit.parent_id == dept_id).first()
    if children:
        raise HTTPException(status_code=400, detail="Không thể xóa vì đang có đơn vị cấp dưới trực thuộc!")
        
    db.delete(dept)
    db.commit()
    return {"status": "success"}