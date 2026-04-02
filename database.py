from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import urllib.parse  # Thêm thư viện này

# 1. Khai báo các thông tin riêng biệt
user = "admin"
password = "Donghung@1234#" # Mật khẩu chứa ký tự đặc biệt
host = "192.168.12.209"
port = "3306"
db_name = "hrm_db"

# 2. Mã hóa mật khẩu (dấu # sẽ biến thành %23)
safe_password = urllib.parse.quote_plus(password)

# 3. Tạo chuỗi URL kết nối an toàn
SQLALCHEMY_DATABASE_URL = f"mysql+pymysql://{user}:{safe_password}@{host}:{port}/{db_name}?charset=utf8mb4"

# 4. Tạo Engine
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_size=50,          
    max_overflow=100,     
    pool_timeout=30,       
    pool_recycle=1800,     
    pool_pre_ping=True
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()