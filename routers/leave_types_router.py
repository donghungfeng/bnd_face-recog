import sqlite3
from fastapi import APIRouter, Request, HTTPException
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

router = APIRouter(prefix="/leave-types", tags=["Leave Types"])
templates = Jinja2Templates(directory="templates")

# Hàm kết nối DB dùng chung
def get_db():
    conn = sqlite3.connect("bnd_kiosk.db")
    conn.row_factory = sqlite3.Row
    return conn

class LeaveTypeModel(BaseModel):
    code: str
    name: str
    benefit_rate: float = 100.0
    max_num_days: int = 0
    scope: str = ""
    status: int = 1
    note: str = ""

@router.get("/")
async def render_page(request: Request):
    return templates.TemplateResponse("leave_types.html", {"request": request})

@router.get("/api")
def get_all():
    with get_db() as conn:
        records = conn.execute("SELECT * FROM leave_types ORDER BY id DESC").fetchall()
        return [dict(row) for row in records]

@router.post("/api")
def create_item(item: LeaveTypeModel):
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO leave_types (code, name, benefit_rate, max_num_days, scope, status, note)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (item.code, item.name, item.benefit_rate, item.max_num_days, item.scope, item.status, item.note))
            conn.commit()
            return {"status": "success", "message": "Thêm mới thành công"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/api/{item_id}")
def update_item(item_id: int, item: LeaveTypeModel):
    with get_db() as conn:
        conn.execute("""
            UPDATE leave_types SET code=?, name=?, benefit_rate=?, max_num_days=?, scope=?, status=?, note=?
            WHERE id=?
        """, (item.code, item.name, item.benefit_rate, item.max_num_days, item.scope, item.status, item.note, item_id))
        conn.commit()
        return {"status": "success", "message": "Cập nhật thành công"}

@router.delete("/api/{item_id}")
def delete_item(item_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM leave_types WHERE id=?", (item_id,))
        conn.commit()
        return {"status": "success", "message": "Đã xóa bản ghi"}