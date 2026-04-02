from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.orm import Session

# Import các module nội bộ
import models
from database import get_db

router = APIRouter(prefix="/leave-types", tags=["Leave Types"])
templates = Jinja2Templates(directory="templates")

class LeaveTypeModel(BaseModel):
    code: str
    name: str
    benefit_rate: float = 100.0
    max_num_days: int = 0
    scope: str = "Toàn viện"
    status: int = 1
    note: str = ""

@router.get("/")
async def render_page(request: Request):
    return templates.TemplateResponse("leave_types.html", {"request": request})

@router.get("/api")
def get_all(db: Session = Depends(get_db)):
    # Dùng SQLAlchemy ORM lấy tất cả và sắp xếp giảm dần theo ID
    records = db.query(models.LeaveType).order_by(models.LeaveType.id.desc()).all()
    return records

@router.post("/api")
def create_item(item: LeaveTypeModel, db: Session = Depends(get_db)):
    try:
        new_leave_type = models.LeaveType(
            code=item.code,
            name=item.name,
            benefit_rate=item.benefit_rate,
            max_num_days=item.max_num_days,
            scope=item.scope,
            status=item.status,
            note=item.note
        )
        
        db.add(new_leave_type)
        db.commit()
        db.refresh(new_leave_type)
        
        return {"status": "success", "message": "Thêm mới loại nghỉ phép thành công"}
        
    except Exception as e:
        db.rollback() 
        raise HTTPException(status_code=400, detail=f"Lỗi cơ sở dữ liệu: {str(e)}")

@router.put("/api/{item_id}")
def update_item(item_id: int, item: LeaveTypeModel, db: Session = Depends(get_db)):
    try:
        record = db.query(models.LeaveType).filter(models.LeaveType.id == item_id).first()
        if not record:
            raise HTTPException(status_code=404, detail="Không tìm thấy loại nghỉ phép này")
        
        record.code = item.code
        record.name = item.name
        record.benefit_rate = item.benefit_rate
        record.max_num_days = item.max_num_days
        record.scope = item.scope
        record.status = item.status
        record.note = item.note
        
        db.commit()
        return {"status": "success", "message": "Cập nhật thành công"}
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Lỗi cơ sở dữ liệu: {str(e)}")

@router.delete("/api/{item_id}")
def delete_item(item_id: int, db: Session = Depends(get_db)):
    try:
        record = db.query(models.LeaveType).filter(models.LeaveType.id == item_id).first()
        if not record:
            raise HTTPException(status_code=404, detail="Không tìm thấy loại nghỉ phép này")
            
        db.delete(record)
        db.commit()
        return {"status": "success", "message": "Đã xóa bản ghi"}
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Lỗi cơ sở dữ liệu: {str(e)}")