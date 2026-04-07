import cv2
import numpy as np
import base64
import os
import pickle
from datetime import datetime
from deepface import DeepFace

# Nhớ bổ sung DB_PATH_IPAD và CACHE_FILE_IPAD vào file config.py
from config import DB_PATH, HISTORY_PATH, MODEL_NAME, CACHE_FILE, DB_IPAD_PATH, IPAD_FILE
from database import SessionLocal
from models import AppConfig, Attendance, Employee

# ==========================================
# 1. KHAI BÁO BIẾN RAM CACHE
# ==========================================
# --- RAM CACHE CHUNG (Dành cho Server/Web) ---
known_file_keys = [] 
known_user_ids = []  
known_embeddings_matrix = np.array([])

# --- RAM CACHE RIÊNG CHO IPAD ---
ipad_file_keys = [] 
ipad_user_ids = []  
ipad_embeddings_matrix = np.array([])

# ==========================================
# 2. LOGIC QUẢN LÝ KHUÔN MẶT & EMBEDDINGS
# ==========================================
def get_base_user_id(file_key):
    """Hàm phụ trợ: Cắt đuôi _1, _2 để lấy mã NV gốc (VD: NV001_2 -> NV001)"""
    parts = file_key.rsplit("_", 1)
    if len(parts) == 2 and parts[1].isdigit():
        return parts[0]
    return file_key

def process_embeddings(db_folder, cache_path, list_name="MAIN"):
    """
    Hàm lõi: Đọc folder, tạo cache và trả về ma trận dùng cho RAM.
    Có thể dùng cho cả luồng MAIN và luồng IPAD.
    """
    keys = []
    user_ids = []
    matrix = np.array([])
    temp_dict = {}

    # 1. Đọc Cache nếu có
    if os.path.exists(cache_path):
        print(f"-> [{list_name}] Đang nạp dữ liệu từ Cache (nhanh)...")
        try:
            with open(cache_path, "rb") as f:
                temp_dict = pickle.load(f)
        except Exception as e:
            print(f"[{list_name}] Lỗi đọc cache, sẽ tạo mới...", e)
    else:
        print(f"-> [{list_name}] Không tìm thấy Cache, sẽ tạo mới...")

    # Đảm bảo thư mục tồn tại
    os.makedirs(db_folder, exist_ok=True)

    # 2. Quét ảnh trong thư mục để tìm ảnh mới
    changed = False
    for filename in os.listdir(db_folder):
        if filename.endswith((".jpg", ".png", ".jpeg")):
            file_key = os.path.splitext(filename)[0]
            if file_key not in temp_dict:
                print(f"-> [{list_name}] Phát hiện ảnh mới [{file_key}], đang mã hóa...")
                img_path = os.path.join(db_folder, filename)
                try:
                    embedding = DeepFace.represent(
                        img_path=img_path, 
                        model_name=MODEL_NAME, 
                        enforce_detection=False, 
                        detector_backend="skip"
                    )[0]["embedding"]
                    temp_dict[file_key] = np.array(embedding)
                    changed = True
                except Exception as e:
                    print(f"[{list_name}] Lỗi khi xử lý {filename}: {e}")
    
    # 3. Chuyển đổi sang định dạng mảng & ma trận numpy
    if temp_dict:
        keys = list(temp_dict.keys())
        user_ids = [get_base_user_id(k) for k in keys]
        matrix = np.array(list(temp_dict.values()))
    
    # 4. Lưu lại cache nếu có thay đổi
    if changed:
        with open(cache_path, "wb") as f:
            pickle.dump(temp_dict, f)
        print(f"-> [{list_name}] Đã lưu cache {len(keys)} khuôn mặt xuống ổ cứng.")

    print(f"-> [{list_name}] SẴN SÀNG! Đã nạp {len(keys)} khuôn mặt vào RAM (Shape: {matrix.shape if matrix.size > 0 else (0,) }).")
    return keys, user_ids, matrix

def load_main_embeddings():
    """Chỉ load dữ liệu cho luồng Server/Web (MAIN)"""
    global known_file_keys, known_user_ids, known_embeddings_matrix
    
    known_file_keys, known_user_ids, known_embeddings_matrix = process_embeddings(
        db_folder=DB_PATH, 
        cache_path=CACHE_FILE, 
        list_name="MAIN"
    )

def load_ipad_embeddings():
    """Chỉ load dữ liệu cho luồng thiết bị iPad (IPAD)"""
    global ipad_file_keys, ipad_user_ids, ipad_embeddings_matrix
    
    ipad_file_keys, ipad_user_ids, ipad_embeddings_matrix = process_embeddings(
        db_folder=DB_IPAD_PATH, 
        cache_path=IPAD_FILE, 
        list_name="IPAD"
    )
    
def load_all_embeddings():
    """
    Được gọi 1 lần khi khởi động Server để nạp cả 2 luồng dữ liệu vào RAM
    """
    global known_file_keys, known_user_ids, known_embeddings_matrix
    global ipad_file_keys, ipad_user_ids, ipad_embeddings_matrix
    
    # Nạp luồng Main
    known_file_keys, known_user_ids, known_embeddings_matrix = process_embeddings(
        db_folder=DB_PATH, 
        cache_path=CACHE_FILE, 
        list_name="MAIN"
    )

    # Nạp luồng iPad
    ipad_file_keys, ipad_user_ids, ipad_embeddings_matrix = process_embeddings(
        db_folder=DB_IPAD_PATH, 
        cache_path=IPAD_FILE, 
        list_name="IPAD"
    )

# ==========================================
# 3. CÁC HÀM TIỆN ÍCH & BACKGROUND LOGGING
# ==========================================
def decode_base64(data: str):
    if "," in data: data = data.split(",")[1]
    img_bytes = base64.b64decode(data)
    nparr = np.frombuffer(img_bytes, np.uint8)
    return cv2.imdecode(nparr, cv2.IMREAD_COLOR)

def background_logging(
    user_id: str, 
    img_full: np.ndarray, 
    confidence: float,
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

        date_folder = now.strftime("%Y-%m-%d")
        timestamp_str = now.strftime("%Y%m%d_%H%M%S")
        success_filename = f"{user_id}_{timestamp_str}.jpg"
        daily_history_path = os.path.join(HISTORY_PATH, date_folder)
        os.makedirs(daily_history_path, exist_ok=True)

        success_filepath = os.path.join(daily_history_path, success_filename)
        
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

        image_web_path = f"/data/history_db/{date_folder}/{success_filename}"
        
        if user_id == 'UNKNOWN':
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

        elif len(records_today) < 6: 
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
            # Ghi đè vào bản ghi thứ 6 (index 5) nếu nhân viên quét từ lần thứ 7 trở đi
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

            # Dọn dẹp nếu database lỡ có nhiều hơn 6 bản ghi
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

# ==========================================
# 4. HỆ THỐNG CẤU HÌNH (CONFIGS)
# ==========================================
sys_configs = {
    "FACE_THRESHOLD": "0.75",       
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


def save_cache(device: str = "main"):
    """
    Lưu RAM cache xuống ổ cứng tùy theo luồng thiết bị.
    :param device: "main" (dành cho Web/Server) hoặc "ipad" (dành riêng cho iPad)
    """
    global known_file_keys, known_embeddings_matrix
    global ipad_file_keys, ipad_embeddings_matrix

    if device == "ipad":
        # Tạo dictionary từ mảng RAM của iPad
        temp_dict = dict(zip(ipad_file_keys, ipad_embeddings_matrix))
        target_file = IPAD_FILE
        prefix = "IPAD"
    else:
        # Tạo dictionary từ mảng RAM của hệ thống chính (main)
        temp_dict = dict(zip(known_file_keys, known_embeddings_matrix))
        target_file = CACHE_FILE
        prefix = "MAIN"

    try:
        with open(target_file, "wb") as f:
            pickle.dump(temp_dict, f)
        print(f"-> [{prefix}] Đã lưu cache {len(temp_dict)} khuôn mặt xuống ổ cứng.")
    except Exception as e:
        print(f"-> [{prefix}] Lỗi khi lưu cache xuống {target_file}: {e}")