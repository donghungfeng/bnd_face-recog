import os

DB_PATH = "./data/face_db"
DB_IPAD_PATH = "./data/ipads_db"
HISTORY_PATH = "./data/history_db"
TEMPLATE_PATH = "./templates"
MODEL_NAME = "ArcFace"
CACHE_FILE = os.path.join(DB_PATH, "embeddings_cache.pkl")
IPAD_FILE = os.path.join(DB_IPAD_PATH, "embeddings_ipads.pkl")

# Tự động tạo thư mục nếu chưa có
for path in [DB_PATH, DB_IPAD_PATH, HISTORY_PATH, TEMPLATE_PATH]:
    if not os.path.exists(path):
        os.makedirs(path)