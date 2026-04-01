import sqlite3
from fastapi import APIRouter, Request, HTTPException
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/leave-requests", tags=["Leave Requests"])
templates = Jinja2Templates(directory="templates")

def get_db():
    conn = sqlite3.connect("bnd_kiosk.db")
    conn.row_factory = sqlite3.Row
    return conn

class LeaveRequestModel(BaseModel):
    username: str
    fullname: str
    from_date: str
    to_date: str
    type_id: int
    reason: str

class LeaveActionModel(BaseModel):
    status: str # 'APPROVED' hoặc 'REJECTED'
    approver_username: str
    approver_fullname: str

@router.get("/")
async def render_page(request: Request):
    return templates.TemplateResponse("leave_requests.html", {"request": request})

@router.get("/api")
def get_all_requests():
    with get_db() as conn:
        # JOIN để lấy tên loại nghỉ phép ra cho dễ nhìn
        query = """
            SELECT r.*, t.name as type_name, t.code as type_code 
            FROM leave_requests r 
            LEFT JOIN leave_types t ON r.type_id = t.id
            ORDER BY r.id DESC
        """
        records = conn.execute(query).fetchall()
        return [dict(row) for row in records]

@router.post("/api")
def create_request(item: LeaveRequestModel):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO leave_requests (username, fullname, from_date, to_date, type_id, reason, status)
            VALUES (?, ?, ?, ?, ?, ?, 'PENDING')
        """, (item.username, item.fullname, item.from_date, item.to_date, item.type_id, item.reason))
        conn.commit()
        return {"status": "success", "message": "Đã tạo đơn xin nghỉ"}

@router.put("/api/{request_id}/status")
def process_request(request_id: int, action: LeaveActionModel):
    with get_db() as conn:
        conn.execute("""
            UPDATE leave_requests 
            SET status=?, approver_username=?, approver_fullname=?
            WHERE id=?
        """, (action.status, action.approver_username, action.approver_fullname, request_id))
        conn.commit()
        return {"status": "success", "message": f"Đã {action.status} đơn nghỉ"}