import os

DB_PATH = "./data/face_db"
HISTORY_PATH = "./data/history_db"
TEMPLATE_PATH = "./templates"
MODEL_NAME = "Facenet512"
CACHE_FILE = os.path.join(DB_PATH, "embeddings_cache.pkl")

# Tự động tạo thư mục nếu chưa có
for path in [DB_PATH, HISTORY_PATH, TEMPLATE_PATH]:
    if not os.path.exists(path):
        os.makedirs(path)