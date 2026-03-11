import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from database import engine, Base
from services import load_embeddings
from routers import attendance_router, auth_router, department_router, employee_router, page_router, face_router, admin_router, shift_router

# 1. Khởi tạo App
app = FastAPI(title="BND HRM AI Face Recognition")

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

# 5. Khởi động AI Cache khi chạy Server
load_embeddings()

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)