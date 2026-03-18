from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import jwt

from database import get_db
from models import Employee

router = APIRouter()

from fastapi.security import OAuth2PasswordBearer

# Cấu hình "Chìa khóa bí mật" để mã hóa Token (Trong thực tế nên lưu ở file biến môi trường .env)
SECRET_KEY = "HRM_BENH_VIEN_SECRET_KEY_2026"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24 # Hết hạn sau 24h

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login")

def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        role: str = payload.get("role")
        if username is None:
            raise HTTPException(status_code=401, detail="Phiên đăng nhập không hợp lệ")
        return {"username": username, "role": role}
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Phiên đăng nhập đã hết hạn")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token không hợp lệ")

class LoginRequest(BaseModel):
    username: str
    password: str

@router.post("/api/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    # 1. Kiểm tra tài khoản có tồn tại không
    user = db.query(Employee).filter(Employee.username == req.username).first()
    
    # So sánh mật khẩu (Tạm thời dùng plain-text theo DB hiện tại)
    if not user or user.password != req.password:
        raise HTTPException(status_code=401, detail="Tài khoản hoặc mật khẩu không chính xác!")
    
    # 2. Kiểm tra xem tài khoản có đang bị Admin khóa không
    if user.is_locked == 1:
        raise HTTPException(status_code=403, detail="Tài khoản của bạn đã bị khóa. Vui lòng liên hệ Quản trị viên!")

    # 3. Tạo JWT Token với thời hạn 24h
    expire = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    payload = {
        "sub": user.username,        # Mã NV
        "role": user.role,           # Quyền (admin, manager, user)
        "full_name": user.full_name, # Tên hiển thị
        "exp": expire                # Thời hạn
    }
    
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

    # 4. Trả Token về cho trình duyệt lưu trữ
    return {
        "access_token": token,
        "token_type": "bearer",
        "username": user.username,
        "full_name": user.full_name,
        "role": user.role
    }