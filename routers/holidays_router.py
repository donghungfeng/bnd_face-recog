from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.orm import Session

# Import các thành phần nội bộ của dự án
import models
from database import get_db

router = APIRouter(prefix="/holidays", tags=["Holidays"])
templates = Jinja2Templates(directory="templates")

# Schema nhận dữ liệu từ Frontend
class HolidayModel(BaseModel):
    code: str
    name: str
    from_date: str
    to_date: str
    num_days: float  # Dùng float để hỗ trợ nghỉ nửa ngày (0.5)
    scope: str = "Toàn viện"
    status: int = 1
    # Lưu ý: Cột 'year' và 'note' không có trong bảng SQL holidays mà bạn gửi lần trước 
    # nên tôi đã bỏ ra khỏi schema này để tránh lỗi. Nếu DB có thì bạn thêm lại nhé.

@router.get("/")
async def render_page(request: Request):
    return templates.TemplateResponse("holidays.html", {"request": request})

@router.get("/api")
def get_all(db: Session = Depends(get_db)):
    # ORM: Lấy tất cả và sắp xếp giảm dần theo from_date
    records = db.query(models.Holiday).order_by(models.Holiday.from_date.desc()).all()
    return records

@router.post("/api")
def create_item(item: HolidayModel, db: Session = Depends(get_db)):
    try:
        # ORM: Khởi tạo object Holiday
        new_holiday = models.Holiday(
            code=item.code,
            name=item.name,
            from_date=item.from_date,
            to_date=item.to_date,
            num_days=item.num_days,
            scope=item.scope,
            status=item.status
        )
        
        db.add(new_holiday)
        db.commit()
        db.refresh(new_holiday)
        
        return {"status": "success", "message": "Thêm mới ngày nghỉ lễ thành công"}
        
    except Exception as e:
        db.rollback() 
        return {"status": "error", "message": f"Lỗi cơ sở dữ liệu: {str(e)}"}

@router.put("/api/{item_id}")
def update_item(item_id: int, item: HolidayModel, db: Session = Depends(get_db)):
    try:
        # ORM: Tìm bản ghi cần sửa
        record = db.query(models.Holiday).filter(models.Holiday.id == item_id).first()
        if not record:
            raise HTTPException(status_code=404, detail="Không tìm thấy ngày lễ này")
        
        # Cập nhật thông tin
        record.code = item.code
        record.name = item.name
        record.from_date = item.from_date
        record.to_date = item.to_date
        record.num_days = item.num_days
        record.scope = item.scope
        record.status = item.status
        
        db.commit()
        return {"status": "success", "message": "Cập nhật ngày lễ thành công"}
        
    except Exception as e:
        db.rollback()
        return {"status": "error", "message": f"Lỗi cơ sở dữ liệu: {str(e)}"}

@router.delete("/api/{item_id}")
def delete_item(item_id: int, db: Session = Depends(get_db)):
    try:
        # ORM: Tìm và xóa bản ghi
        record = db.query(models.Holiday).filter(models.Holiday.id == item_id).first()
        if not record:
            raise HTTPException(status_code=404, detail="Không tìm thấy ngày lễ này")
        
        db.delete(record)
        db.commit()
        return {"status": "success", "message": "Đã xóa ngày lễ thành công"}
        
    except Exception as e:
        db.rollback()
        return {"status": "error", "message": f"Lỗi cơ sở dữ liệu: {str(e)}"}