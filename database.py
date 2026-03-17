import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# nạp các biến môi trường từ file .env
load_dotenv()

# Lấy URL từ biến môi trường DATABASE_URL
# Nếu không tìm thấy, mặc định dùng SQLite để tránh lỗi crash server
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/hrm.db")

# Kiểm tra xem đang dùng loại Database nào để cấu hình Engine cho đúng
if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    # Cấu hình riêng cho SQLite:
    # connect_args={"check_same_thread": False} bắt buộc phải có để FastAPI (đa luồng) chạy được với SQLite
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL, 
        connect_args={"check_same_thread": False}
    )
else:
    # Cấu hình cho MySQL (giữ nguyên pool như bạn đã làm)
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        pool_pre_ping=True,
        pool_recycle=3600
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()