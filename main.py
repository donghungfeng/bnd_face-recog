import uvicorn
import os # Thêm để kiểm tra loại DB
from contextlib import asynccontextmanager
from fastapi import FastAPI
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. Tạo Database Tables 
# TUYỆT ĐỐI KHÔNG mở dòng này. Để Flyway quản lý 100%.
# Base.metadata.create_all(bind=engine) 

# 3. Mount Static Files
app.mount("/data/history_db", StaticFiles(directory="data/history_db"), name="history_db")
app.mount("/data/explanation_db", StaticFiles(directory="data/explanation_db"), name="explanation_db")

# 4. Gắn các Router
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
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)