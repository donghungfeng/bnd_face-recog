# Sử dụng Python 3.10 slim (Nhẹ, tối ưu cho CPU)
FROM python:3.10-slim

# Thiết lập biến môi trường để Python không tạo file .pyc và in log trực tiếp
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Thiết lập thư mục làm việc trong container
WORKDIR /app

# Cài đặt các thư viện hệ thống lõi cần thiết cho OpenCV, YOLO và DeepFace
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy file requirements.txt vào trước để tận dụng cache của Docker
COPY requirements.txt .

# Cài đặt các thư viện Python (Sử dụng --no-cache-dir để giảm dung lượng Image)
RUN pip install --no-cache-dir -r requirements.txt

# --- BÍ KÍP TỐI ƯU ---
# Tải trước mô hình YOLOv8 Nano ngay lúc Build Docker để lần chạy đầu tiên không bị lag
RUN python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"

# Copy toàn bộ mã nguồn dự án vào Container
COPY . .

# Mở cổng 8000 cho FastAPI
EXPOSE 8000

# Lệnh khởi chạy server bằng Uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]