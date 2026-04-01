import sqlite3
from fastapi import APIRouter, Request, HTTPException
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

router = APIRouter(prefix="/holidays", tags=["Holidays"])
templates = Jinja2Templates(directory="templates")

# Hàm kết nối DB dùng chung
def get_db():
    conn = sqlite3.connect("bnd_kiosk.db")
    conn.row_factory = sqlite3.Row
    return conn

class HolidayModel(BaseModel):
    year: int
    code: str
    name: str
    from_date: str
    to_date: str
    num_days: float  # Dùng float để hỗ trợ nghỉ nửa ngày (0.5)
    scope: str = "Toàn viện"
    status: int = 1
    note: str = ""

@router.get("/")
async def render_page(request: Request):
    return templates.TemplateResponse("holidays.html", {"request": request})

@router.get("/api")
def get_all():
    with get_db() as conn:
        # Sắp xếp theo ngày bắt đầu nghỉ giảm dần để dễ xem lễ gần nhất
        records = conn.execute("SELECT * FROM holidays ORDER BY from_date DESC").fetchall()
        return [dict(row) for row in records]

@router.post("/api")
def create_item(item: HolidayModel):
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO holidays (code, name, from_date, to_date, num_days, scope, status, note)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (item.code, item.name, item.from_date, item.to_date, item.num_days, item.scope, item.status, item.note))
            conn.commit()
            return {"status": "success", "message": "Thêm mới thành công"}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Mã nghỉ lễ đã tồn tại!")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/api/{item_id}")
def update_item(item_id: int, item: HolidayModel):
    with get_db() as conn:
        conn.execute("""
            UPDATE holidays 
            SET code=?, name=?, from_date=?, to_date=?, num_days=?, scope=?, status=?, note=?
            WHERE id=?
        """, (item.code, item.name, item.from_date, item.to_date, item.num_days, item.scope, item.status, item.note, item_id))
        conn.commit()
        return {"status": "success", "message": "Cập nhật thành công"}

@router.delete("/api/{item_id}")
def delete_item(item_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM holidays WHERE id=?", (item_id,))
        conn.commit()
        return {"status": "success", "message": "Đã xóa bản ghi"}