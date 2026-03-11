import cv2
import numpy as np
import base64
import os
import pickle
from datetime import datetime
from deepface import DeepFace

from config import DB_PATH, HISTORY_PATH, MODEL_NAME, CACHE_FILE
from database import SessionLocal
from models import Attendance, Employee

# --- BIẾN RAM CACHE ĐÃ ĐƯỢC NÂNG CẤP LÊN MA TRẬN NUMPY ---
known_file_keys = [] # Quản lý tên file thực tế: ['NV001', 'NV001_2', 'NV002_1']
known_user_ids = []  # Quản lý mã NV gốc (để trả về cho AI): ['NV001', 'NV001', 'NV002']
known_embeddings_matrix = np.array([])

def save_cache():
    # Lưu dưới dạng Dictionary cho dễ quản lý trên ổ cứng (Key là tên file chi tiết)
    temp_dict = dict(zip(known_file_keys, known_embeddings_matrix))
    with open(CACHE_FILE, "wb") as f:
        pickle.dump(temp_dict, f)
    print(f"-> Đã lưu cache {len(known_file_keys)} khuôn mặt xuống ổ cứng.")

def get_base_user_id(file_key):
    # Hàm phụ trợ: Cắt đuôi _1, _2 nếu có để lấy user_id gốc (VD: NV001_2 -> NV001)
    parts = file_key.rsplit("_", 1)
    if len(parts) == 2 and parts[1].isdigit():
        return parts[0]
    return file_key

def load_embeddings():
    global known_file_keys, known_user_ids, known_embeddings_matrix
    
    known_file_keys.clear()
    known_user_ids.clear() 
    known_embeddings_matrix = np.array([])
    
    temp_dict = {}
    if os.path.exists(CACHE_FILE):
        print("-> Đang nạp dữ liệu từ Cache (nhanh)...")
        try:
            with open(CACHE_FILE, "rb") as f:
                temp_dict = pickle.load(f)
        except Exception as e:
            print("Lỗi đọc cache, sẽ tạo mới...", e)
    else:
        print("-> Không tìm thấy Cache, sẽ tạo mới...")

    changed = False
    for filename in os.listdir(DB_PATH):
        if filename.endswith(".jpg"):
            file_key = os.path.splitext(filename)[0]
            if file_key not in temp_dict:
                print(f"-> Phát hiện ảnh mới [{file_key}], đang mã hóa...")
                img_path = os.path.join(DB_PATH, filename)
                try:
                    embedding = DeepFace.represent(img_path=img_path, model_name=MODEL_NAME, enforce_detection=False)[0]["embedding"]
                    temp_dict[file_key] = np.array(embedding)
                    changed = True
                except Exception as e:
                    print(f"Lỗi khi xử lý {filename}: {e}")
    
    # Chuyển đổi Dictionary thành Ma trận để dùng cho AI
    if temp_dict:
        known_file_keys = list(temp_dict.keys())
        known_user_ids = [get_base_user_id(k) for k in known_file_keys]
        known_embeddings_matrix = np.array(list(temp_dict.values()))
    
    if changed:
        save_cache()
    print(f"-> SẴN SÀNG! Đã nạp {len(known_file_keys)} khuôn mặt vào RAM (Shape: {known_embeddings_matrix.shape}).")

def decode_base64(data: str):
    if "," in data: data = data.split(",")[1]
    img_bytes = base64.b64decode(data)
    nparr = np.frombuffer(img_bytes, np.uint8)
    return cv2.imdecode(nparr, cv2.IMREAD_COLOR)

def background_logging(user_id: str, img_full: np.ndarray, confidence: float):
    db = SessionLocal() 
    try:
        now = datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)

        records_today = db.query(Attendance).filter(
            Attendance.username == user_id,
            Attendance.check_in_time >= today_start,
            Attendance.check_in_time <= today_end
        ).order_by(Attendance.check_in_time.asc()).all()

        timestamp_str = now.strftime("%Y%m%d_%H%M%S")
        success_filename = f"{user_id}_{timestamp_str}.jpg"
        success_filepath = os.path.join(HISTORY_PATH, success_filename)
        cv2.imwrite(success_filepath, img_full)

        employee = db.query(Employee).filter(Employee.username == user_id).first()
        full_name = employee.full_name if employee else "Chưa cập nhật tên"

        late_min, early_min = 0, 0
        time_7_30 = now.replace(hour=7, minute=30, second=0, microsecond=0)
        time_17_00 = now.replace(hour=17, minute=0, second=0, microsecond=0)
        time_12_00 = now.replace(hour=12, minute=0, second=0, microsecond=0)

        if now < time_12_00 and now > time_7_30:
            late_min = int((now - time_7_30).total_seconds() / 60)
        elif now >= time_12_00 and now < time_17_00:
            early_min = int((time_17_00 - now).total_seconds() / 60)

        image_web_path = f"/data/history_db/{success_filename}"

        if len(records_today) < 2:
            new_log = Attendance(
                username=user_id, full_name=full_name, check_in_time=now,
                image_path=image_web_path, late_minutes=late_min, early_minutes=early_min, confidence=round(confidence*100, 2)
            )
            db.add(new_log)
        else:
            latest_record = records_today[1] 
            if latest_record.image_path:
                old_img_path = "." + latest_record.image_path 
                if os.path.exists(old_img_path): os.remove(old_img_path)

            latest_record.check_in_time = now
            latest_record.image_path = image_web_path
            latest_record.late_minutes = late_min
            latest_record.early_minutes = early_min
            latest_record.confidence = round(confidence*100, 2)

            if len(records_today) > 2:
                for extra_record in records_today[2:]:
                    if extra_record.image_path:
                        extra_img_path = "." + extra_record.image_path
                        if os.path.exists(extra_img_path): os.remove(extra_img_path)
                    db.delete(extra_record)
        db.commit()
    except Exception as e:
        print(f"Lỗi ghi log ngầm: {e}")
    finally:
        db.close()