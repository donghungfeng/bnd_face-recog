import uvicorn
import os # Thêm để kiểm tra loại DB
import time
import logging
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from database import engine, Base
from services import load_all_embeddings, load_system_configs
from routers import (
    attendance_router, auth_router, config_router, 
    department_router, employee_router, holidays_router, leave_requests_router, leave_types_router, page_router, 
    face_router, admin_router, shift_router, monthly_record_router, explanation_router, wifi_router
)

# ==========================================
# CẤU HÌNH LOGGING TÙY CHỈNH
# ==========================================
log_format = "[%(asctime)s] %(levelname)s: %(message)s"
date_format = "%Y-%m-%d %H:%M:%S"
formatter = logging.Formatter(fmt=log_format, datefmt=date_format)

logger = logging.getLogger("api_logger")
logger.setLevel(logging.INFO)

if not logger.handlers:
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

# ==========================================
# 0. ĐỊNH NGHĨA VÒNG ĐỜI (LIFESPAN)
# ==========================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Kiểm tra loại DB đang dùng từ chuỗi kết nối
    db_type = "SQLite" if engine.url.drivername.startswith("sqlite") else "MySQL"
    
    # --- CHẠY LÚC START SERVER ---
    print(f"🚀 [{db_type} Mode] Đang khởi động Server...")
    
    # Nạp AI Embeddings và Config
    print("🧠 Đang nạp AI Embeddings vào bộ nhớ...")
    load_all_embeddings()
    load_system_configs()
    print(f"✅ Hệ thống AI và Cấu hình đã sẵn sàng trên {db_type}!")
    
    yield 
    
    # --- CHẠY LÚC STOP SERVER ---
    print(f"🛑 Server đang tắt, đang đóng kết nối {db_type} Pool...")
    try:
        engine.dispose()
        print("✅ Đã ngắt kết nối Database an toàn!")
    except Exception as e:
        print(f"⚠️ Lỗi khi đóng Database: {e}")

# ==========================================
# 1. KHỞI TẠO APP
# ==========================================
# Để title động cho chuyên nghiệp
app = FastAPI(title="BND HRM AI Face Recognition", lifespan=lifespan)

# ==========================================
# 2. MIDDLEWARE ĐO THỜI GIAN & GHI LOG
# ==========================================
async def log_requests(request: Request, call_next):
    start_time = time.time()
    
    # 1. Khởi tạo giá trị mặc định là GUEST (Khách)
    request.state.user_id = "GUEST"
    
    # 2. Đẩy request vào trong cho các Router xử lý
    response = await call_next(request)
    
    # 3. Request đã quay trở ra, tính toán thời gian
    process_time = (time.time() - start_time) * 1000
    client_ip = request.client.host if request.client else "127.0.0.1"
    
    # 4. Lấy user_id mà các Router đã lén nhét vào state
    user_id = getattr(request.state, "user_id", "GUEST")
    
    # 5. Ghi log tổng hợp
    logger.info(
        f"[USER: {user_id}] {client_ip} - \"{request.method} {request.url.path}\" "
        f"{response.status_code} - {process_time:.2f}ms"
    )
    
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3. Tạo Database Tables 
# TUYỆT ĐỐI KHÔNG mở dòng này. Để Flyway quản lý 100%.
# Base.metadata.create_all(bind=engine) 

# 4. Mount Static Files
app.mount("/data/history_db", StaticFiles(directory="data/history_db"), name="history_db")
app.mount("/data/explanation_db", StaticFiles(directory="data/explanation_db"), name="explanation_db")
app.mount("/data/leave_requests", StaticFiles(directory="data/leave_requests"), name="leave_requests")

# 5. Gắn các Router
app.include_router(page_router.router)
app.include_router(face_router.router)
app.include_router(admin_router.router)
app.include_router(shift_router.router)
app.include_router(department_router.router)
app.include_router(employee_router.router)
app.include_router(auth_router.router)
app.include_router(attendance_router.router)
app.include_router(config_router.router)
app.include_router(monthly_record_router.router)
app.include_router(explanation_router.router)
app.include_router(wifi_router.router)
app.include_router(leave_types_router.router)
app.include_router(holidays_router.router)
app.include_router(leave_requests_router.router)

if __name__ == "__main__":
    # Đã thêm access_log=False để tắt log mặc định của uvicorn, tránh bị in đúp
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, access_log=False)