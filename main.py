import uvicorn
from contextlib import asynccontextmanager # Thêm thư viện quản lý vòng đời
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text # Thêm để chạy lệnh SQL thuần

# Khai báo thêm SessionLocal để dùng lúc đóng DB
from database import engine, Base, SessionLocal 
from services import load_embeddings
from routers import attendance_router, auth_router, config_router, department_router, employee_router, page_router, face_router, admin_router, shift_router

# ==========================================
# 0. ĐỊNH NGHĨA VÒNG ĐỜI (LIFESPAN) CỦA SERVER
# ==========================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- CHẠY LÚC START SERVER ---
    print("🚀 Đang khởi động Server...")
    print("🧠 Đang nạp AI Embeddings vào bộ nhớ (Cache)...")
    load_embeddings()
    print("✅ Hệ thống AI đã sẵn sàng!")
    
    # Ứng dụng sẽ hoạt động tại đây
    yield 
    
    # --- CHẠY LÚC STOP SERVER (Nhấn Ctrl+C hoặc Docker stop) ---
    print("🛑 Server đang tắt, tiến hành dọn dẹp SQLite WAL...")
    try:
        db = SessionLocal()
        # Ép SQLite gộp ngay lập tức file .db-wal vào file .db gốc
        db.execute(text("PRAGMA wal_checkpoint(TRUNCATE);"))
        db.commit()
        db.close()
        
        # Đóng toàn bộ Pool kết nối của SQLAlchemy
        engine.dispose()
        print("✅ Đã dọn dẹp và ngắt kết nối Database an toàn!")
    except Exception as e:
        print(f"⚠️ Lỗi khi đóng Database: {e}")

# ==========================================
# 1. KHỞI TẠO APP (Gắn Lifespan vào đây)
# ==========================================
app = FastAPI(title="BND HRM AI Face Recognition", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. Tạo Database Tables
Base.metadata.create_all(bind=engine)

# 3. Mount Static Files
app.mount("/data/history_db", StaticFiles(directory="data/history_db"), name="history_db")

# 4. Gắn các Router (Gộp các nhánh API lại)
app.include_router(page_router.router)
app.include_router(face_router.router)
app.include_router(admin_router.router)
app.include_router(shift_router.router)

app.include_router(department_router.router)
app.include_router(employee_router.router)
app.include_router(auth_router.router)
app.include_router(attendance_router.router)
app.include_router(config_router.router)


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)