# Sử dụng Python 3.10 hoặc 3.11 (DeepFace chạy ổn định nhất ở đây)
FROM python:3.10-slim

# 1. Cài đặt các thư viện hệ thống cho OpenCV và MediaPipe
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxrender1 \
    libxext6 \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 2. Tạo thư mục data và cache cho Model DeepFace (Đẩy lên trước để tận dụng cache)
RUN mkdir -p data && mkdir -p /root/.deepface/weights

# 3. Copy requirements và cài đặt (Bước này cực nặng, nên để riêng)
COPY requirements.txt .
# Tăng thời gian timeout vì DeepFace/TensorFlow rất nặng
RUN pip install --no-cache-dir --default-timeout=100 -r requirements.txt

# 4. Copy toàn bộ code HTML, CSS, JS, Python
COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]