import cv2
import numpy as np
import base64
import os
import pickle
from datetime import datetime
from deepface import DeepFace

from config import DB_PATH, HISTORY_PATH, MODEL_NAME, CACHE_FILE
from database import SessionLocal
from models import AppConfig, Attendance, Employee

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
                    embedding = DeepFace.represent(img_path=img_path, model_name=MODEL_NAME, enforce_detection=False, detector_backend="skip")[0]["embedding"]
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

import os
import cv2
import numpy as np
from datetime import datetime
# Nhớ import các module Database của bác (SessionLocal, Attendance, Employee...)

def background_logging(
    user_id: str, 
    img_full: np.ndarray, 
    confidence: float,
    # === BỔ SUNG 4 THAM SỐ MỚI (Có giá trị mặc định để không lỗi code cũ) ===
    client_ip: str = None, 
    latitude: float = None, 
    longitude: float = None, 
    attendance_type: str = "Tập trung",
    note: str = ""
):
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
        
        # [Fix lỗi cũ] Rào chắn bảo vệ OpenCV trước khi lưu ảnh
        if img_full is not None and getattr(img_full, 'size', 0) > 0:
            cv2.imwrite(success_filepath, img_full)
        else:
            print(f"⚠️ Bỏ qua lưu file ảnh cho {user_id} vì dữ liệu ảnh rỗng.")

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

        if user_id == 'UNKNOWN':
            # Trường hợp 1: NGƯỜI LẠ -> Cứ chèn thêm dòng mới vào DB, không đụng tới index [1]
            new_log = Attendance(
                username=user_id, 
                full_name=full_name, 
                check_in_time=now,
                image_path=image_web_path, 
                late_minutes=0, 
                early_minutes=0, 
                confidence=round(confidence*100, 2),
                client_ip=client_ip,                  
                latitude=latitude,                    
                longitude=longitude,                  
                attendance_type=attendance_type,        
                note=note                              
            )
            db.add(new_log)

        elif len(records_today) < 6: # Tăng giới hạn tạo mới lên tối đa 6 bản ghi
            new_log = Attendance(
                username=user_id, 
                full_name=full_name, 
                check_in_time=now,
                image_path=image_web_path, 
                late_minutes=late_min, 
                early_minutes=early_min, 
                confidence=round(confidence*100, 2),
                client_ip=client_ip,                  
                latitude=latitude,                    
                longitude=longitude,                  
                attendance_type=attendance_type,        
                note=note                            
            )
            db.add(new_log)
        else:
            # ---> CẬP NHẬT: Ghi đè vào bản ghi thứ 6 (index 5) nếu nhân viên quét từ lần thứ 7 trở đi
            latest_record = records_today[5] 
            if latest_record.image_path:
                old_img_path = "." + latest_record.image_path 
                if os.path.exists(old_img_path): os.remove(old_img_path)

            latest_record.check_in_time = now
            latest_record.image_path = image_web_path
            latest_record.late_minutes = late_min
            latest_record.early_minutes = early_min
            latest_record.confidence = round(confidence*100, 2)
            
            latest_record.client_ip = client_ip                 
            latest_record.latitude = latitude                   
            latest_record.longitude = longitude                 
            latest_record.attendance_type = attendance_type     
            latest_record.note = note                         

            # Dọn dẹp nếu database lỡ có nhiều hơn 6 bản ghi (xóa từ bản ghi thứ 7 trở đi)
            if len(records_today) > 6:
                for extra_record in records_today[6:]:
                    if extra_record.image_path:
                        extra_img_path = "." + extra_record.image_path
                        if os.path.exists(extra_img_path): os.remove(extra_img_path)
                    db.delete(extra_record)

        db.commit()
    except Exception as e:
        print(f"Lỗi ghi log ngầm: {e}")
    finally:
        db.close()


sys_configs = {
    "FACE_THRESHOLD": "0.75",       # Giá trị mặc định
    "ENABLE_ANTI_SPOOFING": "true",
    "MIN_FACE_RATIO": "0.08"
}

def load_system_configs():
    """Tải cấu hình từ DB lên RAM khi khởi động Server"""
    global sys_configs
    db = SessionLocal()
    try:
        configs = db.query(AppConfig).all()
        for c in configs:
            sys_configs[c.config_key] = c.config_value
        print(f"-> Đã nạp {len(configs)} cấu hình hệ thống vào RAM.")
    except Exception as e:
        print(f"Lỗi nạp cấu hình: {e}")
    finally:
        db.close()

def get_config(key: str, default_value: any):
    """Hàm lấy cấu hình siêu tốc từ RAM"""
    return sys_configs.get(key, default_value)