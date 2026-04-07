import base64
from datetime import datetime
import os
import cv2
import glob
import numpy as np
from fastapi.responses import FileResponse
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends, Request
from fastapi.concurrency import run_in_threadpool
from deepface import DeepFace
from sqlalchemy.orm import Session
from models import Attendance
from schemas import CheckIPRequest, FaceRequest, ScanFraudRequest, SingleFaceDeleteRequest, UnregisterRequest, PersonalVerifyRequest, TestFaceRequest, UpdateImageUrlRequest
from config import DB_IPAD_PATH, DB_PATH, IPAD_FILE, MODEL_NAME, CACHE_FILE
from database import get_db
import time

from ultralytics import YOLO
object_model = YOLO('yolov8n.pt')

import services 

router = APIRouter()

BASE_DIR = os.getcwd()

consecutive_unrecognized = {}

@router.post("/register")
async def register(request: FaceRequest):
    img = services.decode_base64(request.image_base64)
    user_id = request.user_id
    
    existing_files = glob.glob(os.path.join(DB_PATH, f"{user_id}_*.jpg"))
    old_file = os.path.join(DB_PATH, f"{user_id}.jpg")
    if os.path.exists(old_file):
        existing_files.append(old_file)
        
    next_index = 1
    indices = []
    for f in existing_files:
        basename = os.path.basename(f).replace(".jpg", "")
        parts = basename.rsplit("_", 1)
        if len(parts) == 2 and parts[1].isdigit():
            indices.append(int(parts[1]))
            
    if indices:
        next_index = max(indices) + 1
    elif os.path.exists(old_file):
        next_index = 2
        
    if next_index > 3: # Giới hạn 3 ảnh mỗi người
        return {"status": "error", "message": "Đã đạt giới hạn 3 ảnh cho nhân viên này."}
        
    new_filename = f"{user_id}_{next_index}.jpg" if next_index > 1 else f"{user_id}.jpg"
    file_key = new_filename.replace(".jpg", "")
    file_path = os.path.join(DB_PATH, new_filename)
    
    cv2.imwrite(file_path, img)
    
    try:
        results = await run_in_threadpool(DeepFace.represent, img_path=img, model_name=MODEL_NAME, enforce_detection=False)
        embedding = np.array(results[0]["embedding"])
        
        services.known_file_keys.append(file_key)
        services.known_user_ids.append(user_id)
        if services.known_embeddings_matrix.size == 0:
            services.known_embeddings_matrix = np.array([embedding])
        else:
            services.known_embeddings_matrix = np.vstack([services.known_embeddings_matrix, embedding])
            
    except Exception as e:
        if os.path.exists(file_path): os.remove(file_path) # Xóa ảnh nếu AI lỗi
        return {"status": "error", "message": f"Lỗi AI: {e}"}
        
    return {"status": "success", "message": f"Đã đăng ký diện mạo số {next_index} cho {user_id}"}

@router.post("/recognize")
async def recognize(request: FaceRequest, background_tasks: BackgroundTasks):
    global consecutive_unrecognized
    img_crop = services.decode_base64(request.image_base64)
    img_to_save = services.decode_base64(request.full_image_base64) if request.full_image_base64 else img_crop
    max_sim = 0.0
    is_anti_spoof_enabled = services.get_config("ENABLE_ANTI_SPOOFING", "true").lower() == "true"

    try:
        gray = cv2.cvtColor(img_crop, cv2.COLOR_BGR2GRAY)
        sharpness_score = cv2.Laplacian(gray, cv2.CV_64F).var()
        
        if sharpness_score < 50:
            return {"recognized": False, "message": "Ảnh gửi lên hệ thống quá mờ, vui lòng thử lại!"}
    except Exception as e:
        pass 

    try:
        results = await run_in_threadpool(DeepFace.represent, img_path=img_crop, model_name=MODEL_NAME, enforce_detection=True,detector_backend="skip",anti_spoofing=is_anti_spoof_enabled)
        if not results: return {"recognized": False, "message": "Không thấy mặt"}
        
        if is_anti_spoof_enabled and not results[0].get("is_real", True):
             return {"recognized": False, "message": "Phát hiện gian lận hình ảnh!"}

        current_embedding = np.array(results[0]["embedding"])
        
        if len(services.ipad_user_ids) == 0:
            return {"recognized": False, "message": "RAM chưa có dữ liệu, hãy tải lại."}

        dot_products = np.dot(services.ipad_embeddings_matrix, current_embedding)
        matrix_norms = np.linalg.norm(services.ipad_embeddings_matrix, axis=1)
        current_norm = np.linalg.norm(current_embedding)
        
        similarities = dot_products / (matrix_norms * current_norm)
        
        sorted_indices = np.argsort(similarities)[::-1]
        
        best_index = sorted_indices[0]
        max_sim = similarities[best_index]
        best_match = services.ipad_user_ids[best_index]
        
        # Tìm người giống thứ 2 
        second_best_sim = 0.0
        second_best_match = None
        
        for idx in sorted_indices[1:]:
            if services.ipad_user_ids[idx] != best_match:
                second_best_sim = similarities[idx]
                second_best_match = services.ipad_user_ids[idx]
                break 
                
        margin_percent = (max_sim - second_best_sim) * 100
        THRESHOLD = float(services.get_config("FACE_THRESHOLD", "0.75"))
        MARGIN_THRESHOLD = float(services.get_config("FACE_MARGIN_THRESHOLD", "4.0"))
        ABSOLUTE_SAFE_ZONE = 0.85

        ip = request.client_public_ip or "unknown"
        now = time.time()
        
        # 1. Dọn dẹp thùng rác đếm ngược (quá 15s không quét là reset đếm lại)
        for k in list(consecutive_unrecognized.keys()):
            if now - consecutive_unrecognized[k]["last_time"] > 15:
                del consecutive_unrecognized[k]

        # 2. XỬ LÝ NHẬN DIỆN THÀNH CÔNG
        if max_sim >= THRESHOLD:
            # Xóa bộ đếm rác nếu đã thành công
            consecutive_unrecognized.pop(ip, None)

            if max_sim < ABSOLUTE_SAFE_ZONE and second_best_match and margin_percent < MARGIN_THRESHOLD:
                note_str = f"Từ chối do quá giống {second_best_match} (Lệch {round(margin_percent, 2)}% < {MARGIN_THRESHOLD}%)"
                background_tasks.add_task(services.background_logging, "UNKNOWN", img_to_save, max_sim, request.client_public_ip, 0, 0, request.attendance_type, note_str)
                return {
                    "recognized": False, 
                    "message": f"⚠️ GÓC CHỤP BỊ NHIỄU, VUI LÒNG THỬ LẠI", 
                    "match_probability": f"{round(max_sim * 100, 2)}%"
                }

            # Qua mượt -> Chấm công thành công!
            background_tasks.add_task(services.background_logging, best_match, img_to_save, max_sim, request.client_public_ip, 0, 0, request.attendance_type, '')
            return {"recognized": True, "user_id": best_match, "match_probability": f"{round(max_sim * 100, 2)}%"}
        
        # 3. XỬ LÝ TÌNH HUỐNG LẠI GẦN ĐÚNG NHƯNG TRƯỢT (Logic Auto-Renew)
        # Chỉ theo dõi nếu độ giống trên 55% (Loại bỏ trường hợp quét phải cái gối, bức tượng)
        if max_sim > 0.55:
            if ip not in consecutive_unrecognized:
                consecutive_unrecognized[ip] = {"user_id": best_match, "count": 1, "last_time": now}
            else:
                tracker = consecutive_unrecognized[ip]
                if tracker["user_id"] == best_match:
                    tracker["count"] += 1
                    tracker["last_time"] = now
                else:
                    consecutive_unrecognized[ip] = {"user_id": best_match, "count": 1, "last_time": now}
            
            # NẾU TRƯỢT ĐẾN LẦN THỨ 5 MÀ VẪN GIỐNG NGƯỜI NÀY NHẤT -> YÊU CẦU XÁC MINH
            if consecutive_unrecognized[ip]["count"] >= 5:
                consecutive_unrecognized.pop(ip, None) # Xóa bộ đếm
                return {
                    "recognized": "verify_renew", # Gửi status đặc biệt về Frontend
                    "user_id": best_match,
                    "message": f"Hệ thống nghi ngờ bạn là {best_match}. Xác nhận cập nhật khuôn mặt mới?",
                    "match_probability": f"{round(max_sim * 100, 2)}%"
                }
        else:
            consecutive_unrecognized.pop(ip, None)

        # 4. Trường hợp không đủ Threshold (như cũ)
        note_str = f"Nhận dạng thất bại (Giống {best_match} nhất với {round(max_sim * 100, 2)}%)"
        background_tasks.add_task(services.background_logging, "UNKNOWN", img_to_save, max_sim, request.client_public_ip, 0, 0, request.attendance_type, note_str)
        return {"recognized": False, "message": "Người lạ", "match_probability": f"{round(max_sim * 100, 2)}%"}
        
    except Exception as e:
        error_msg = str(e).lower()
        if "spoof detected" in error_msg:
            return {"recognized": False, "message": "CẢNH BÁO GIAN LẬN!"}
        elif "face could not be detected" in error_msg:
            return {"recognized": False, "message": "Không tìm thấy khuôn mặt"}
        else:
            return {"recognized": False, "message": f"Lỗi: {str(e)}"}

@router.post("/unregister")
async def unregister(request: UnregisterRequest):
    user_id = request.user_id
    
    files_to_delete = glob.glob(os.path.join(DB_PATH, f"{user_id}_*.jpg"))
    old_file = os.path.join(DB_PATH, f"{user_id}.jpg")
    if os.path.exists(old_file): files_to_delete.append(old_file)
    
    for f in files_to_delete:
        try: os.remove(f)
        except: pass
        
    indices_to_delete = [i for i, uid in enumerate(services.known_user_ids) if uid == user_id]
    
    if indices_to_delete:
        services.known_embeddings_matrix = np.delete(services.known_embeddings_matrix, indices_to_delete, axis=0)
        for i in sorted(indices_to_delete, reverse=True):
            services.known_file_keys.pop(i)
            services.known_user_ids.pop(i)
            
        services.save_cache()
        return {"status": "success"}
        
    return {"status": "error", "message": "Không tìm thấy người này."}

@router.post("/unregister_ipad")
async def unregister(request: UnregisterRequest):
    user_id = request.user_id
    
    files_to_delete = glob.glob(os.path.join(DB_IPAD_PATH, f"{user_id}_*.jpg"))
    old_file = os.path.join(DB_IPAD_PATH, f"{user_id}.jpg")
    if os.path.exists(old_file): files_to_delete.append(old_file)
    
    for f in files_to_delete:
        try: os.remove(f)
        except: pass
        
    indices_to_delete = [i for i, uid in enumerate(services.ipad_user_ids) if uid == user_id]
    
    if indices_to_delete:
        services.ipad_embeddings_matrix = np.delete(services.ipad_embeddings_matrix, indices_to_delete, axis=0)
        for i in sorted(indices_to_delete, reverse=True):
            services.ipad_file_keys.pop(i)
            services.ipad_user_ids.pop(i)
            
        services.save_cache()
        return {"status": "success"}
        
    return {"status": "error", "message": "Không tìm thấy người này."}

@router.get("/clear_ram")
async def clear_ram():
    services.known_file_keys.clear()
    services.known_user_ids.clear()
    services.known_embeddings_matrix = np.array([])
    if os.path.exists(CACHE_FILE): os.remove(CACHE_FILE)
    return {"status": "success"}


@router.get("/clear_ram_ipad")
async def clear_ram():
    services.ipad_file_keys.clear()
    services.ipad_user_ids.clear()
    services.ipad_embeddings_matrix = np.array([])
    if os.path.exists(IPAD_FILE): os.remove(IPAD_FILE)
    return {"status": "success"}

@router.get("/api/ai_status")
async def get_ai_status():
    import os
    files = [f for f in os.listdir(DB_PATH) if f.endswith(".jpg")]
    
    return {
        "files_count": len(files), 
        "ram_count": len(services.known_file_keys)
    }

@router.get("/api/ai_status_ipad")
async def get_ai_status():
    import os
    files = [f for f in os.listdir(DB_IPAD_PATH) if f.endswith(".jpg")]
    
    return {
        "files_count": len(files), 
        "ram_count": len(services.ipad_file_keys)
    }

@router.get("/reload_ram")
async def reload_ram_api():
    services.load_main_embeddings()
    return {
        "status": "success", 
        "message": f"Đã nạp lại danh sách khuôn mặt vào RAM!"
    }

@router.get("/reload_ram_ipad")
async def reload_ram_api():
    services.load_ipad_embeddings()
    return {
        "status": "success", 
        "message": f"Đã nạp lại danh sách khuôn mặt vào RAM!"
    }

@router.get("/api/faces/image/{filename}")
def get_face_image(filename: str):
    import os
    file_path = os.path.join(DB_PATH, f"{filename}.jpg")
    if os.path.exists(file_path):
        return FileResponse(file_path)
        
    possible_files = [f"{filename}.jpg", f"{filename}_1.jpg", f"{filename}_2.jpg"]
    for pf in possible_files:
        pf_path = os.path.join(DB_PATH, pf)
        if os.path.exists(pf_path):
            return FileResponse(pf_path)
            
    raise HTTPException(status_code=404, detail="Không tìm thấy ảnh")

@router.get("/api/ipad/image/{filename}")
def get_face_image(filename: str):
    import os
    file_path = os.path.join(DB_IPAD_PATH, f"{filename}.jpg")
    if os.path.exists(file_path):
        return FileResponse(file_path)
        
    possible_files = [f"{filename}.jpg", f"{filename}_1.jpg", f"{filename}_2.jpg"]
    for pf in possible_files:
        pf_path = os.path.join(DB_IPAD_PATH, pf)
        if os.path.exists(pf_path):
            return FileResponse(pf_path)
            
    raise HTTPException(status_code=404, detail="Không tìm thấy ảnh")

@router.get("/api/faces/overview")
def get_faces_overview(
    page: int = 1, 
    limit: int = 12, 
    search: str = "", 
    status: str = "all", 
    db: Session = Depends(get_db)
):
    import os
    import math
    from models import Employee
    from sqlalchemy.orm import joinedload
    
    file_map = {}
    if os.path.exists(DB_PATH):
        for f in os.listdir(DB_PATH):
            if f.endswith('.jpg'):
                exact_name = f.replace('.jpg', '')
                parts = exact_name.rsplit("_", 1)
                if len(parts) == 2 and parts[1].isdigit():
                    uid_upper = parts[0].upper()
                else:
                    uid_upper = exact_name.upper()
                    
                if uid_upper not in file_map:
                    file_map[uid_upper] = []
                file_map[uid_upper].append(exact_name)
                
    emps = db.query(Employee).options(joinedload(Employee.department)).all()
    emp_dict_upper = {e.username.upper(): e for e in emps}
    
    all_results = []
    
    # Gộp dữ liệu nhân viên
    for e in emps:
        username_upper = e.username.upper()
        has_face = username_upper in file_map
        all_results.append({
            "type": "mapped" if has_face else "no_face",
            "username": e.username,
            "full_name": e.full_name,
            "department_name": e.department.unit_name if e.department else "Chưa xếp phòng",
            "images": file_map.get(username_upper, [])
        })
        
    # Gộp dữ liệu ảnh mồ côi
    for upper_name, file_names in file_map.items():
        if upper_name not in emp_dict_upper:
            all_results.append({
                "type": "unmapped",
                "username": upper_name,
                "full_name": "Người lạ / Chưa ĐK",
                "department_name": "---",
                "images": file_names
            })
            
    # XỬ LÝ LỌC (FILTERING)
    filtered_results = []
    search_query = search.lower().strip()
    
    for item in all_results:
        # Lọc trạng thái
        if status != "all" and item["type"] != status:
            continue
        # Lọc tìm kiếm
        if search_query:
            if search_query not in item["username"].lower() and search_query not in item["full_name"].lower():
                continue
        
        filtered_results.append(item)
        
    # XỬ LÝ PHÂN TRANG (PAGINATION)
    total_items = len(filtered_results)
    total_pages = math.ceil(total_items / limit) if total_items > 0 else 1
    
    start_idx = (page - 1) * limit
    end_idx = start_idx + limit
    paginated_results = filtered_results[start_idx:end_idx]
            
    return {
        "data": paginated_results,
        "total": total_items,
        "page": page,
        "limit": limit,
        "total_pages": total_pages
    }

@router.get("/api/ipad/overview")
def get_faces_overview(
    page: int = 1, 
    limit: int = 12, 
    search: str = "", 
    status: str = "all", 
    db: Session = Depends(get_db)
):
    import os
    import math
    from models import Employee
    from sqlalchemy.orm import joinedload
    
    file_map = {}
    if os.path.exists(DB_IPAD_PATH):
        for f in os.listdir(DB_IPAD_PATH):
            if f.endswith('.jpg'):
                exact_name = f.replace('.jpg', '')
                parts = exact_name.rsplit("_", 1)
                if len(parts) == 2 and parts[1].isdigit():
                    uid_upper = parts[0].upper()
                else:
                    uid_upper = exact_name.upper()
                    
                if uid_upper not in file_map:
                    file_map[uid_upper] = []
                file_map[uid_upper].append(exact_name)
                
    emps = db.query(Employee).options(joinedload(Employee.department)).all()
    emp_dict_upper = {e.username.upper(): e for e in emps}
    
    all_results = []
    
    # Gộp dữ liệu nhân viên
    for e in emps:
        username_upper = e.username.upper()
        has_face = username_upper in file_map
        all_results.append({
            "type": "mapped" if has_face else "no_face",
            "username": e.username,
            "full_name": e.full_name,
            "department_name": e.department.unit_name if e.department else "Chưa xếp phòng",
            "images": file_map.get(username_upper, [])
        })
        
    # Gộp dữ liệu ảnh mồ côi
    for upper_name, file_names in file_map.items():
        if upper_name not in emp_dict_upper:
            all_results.append({
                "type": "unmapped",
                "username": upper_name,
                "full_name": "Người lạ / Chưa ĐK",
                "department_name": "---",
                "images": file_names
            })
            
    # XỬ LÝ LỌC (FILTERING)
    filtered_results = []
    search_query = search.lower().strip()
    
    for item in all_results:
        # Lọc trạng thái
        if status != "all" and item["type"] != status:
            continue
        # Lọc tìm kiếm
        if search_query:
            if search_query not in item["username"].lower() and search_query not in item["full_name"].lower():
                continue
        
        filtered_results.append(item)
        
    # XỬ LÝ PHÂN TRANG (PAGINATION)
    total_items = len(filtered_results)
    total_pages = math.ceil(total_items / limit) if total_items > 0 else 1
    
    start_idx = (page - 1) * limit
    end_idx = start_idx + limit
    paginated_results = filtered_results[start_idx:end_idx]
            
    return {
        "data": paginated_results,
        "total": total_items,
        "page": page,
        "limit": limit,
        "total_pages": total_pages
    }

@router.post("/delete_single_face")
async def delete_single_face(request: SingleFaceDeleteRequest):
    filename = request.filename
    file_path = os.path.join(DB_PATH, f"{filename}.jpg")
    
    if os.path.exists(file_path):
        os.remove(file_path)
        
    if filename in services.known_file_keys:
        idx = services.known_file_keys.index(filename)
        
        # Rút phần tử khỏi mảng
        services.known_file_keys.pop(idx)
        services.known_user_ids.pop(idx)
        services.known_embeddings_matrix = np.delete(services.known_embeddings_matrix, idx, axis=0)
        
        # Lưu lại cache
        services.save_cache("main")
        
    return {"status": "success", "message": f"Đã xóa ảnh {filename}"}

@router.post("/delete_single_ipad_face")
async def delete_single_ipad_face(request: SingleFaceDeleteRequest):
    filename = request.filename
    file_path = os.path.join(DB_IPAD_PATH, f"{filename}.jpg")
    
    if os.path.exists(file_path):
        os.remove(file_path)
        
    if filename in services.ipad_file_keys:
        idx = services.ipad_file_keys.index(filename)
        
        # Rút phần tử khỏi mảng
        services.ipad_file_keys.pop(idx)
        services.ipad_user_ids.pop(idx)
        services.ipad_embeddings_matrix = np.delete(services.ipad_embeddings_matrix, idx, axis=0)
        
        # Lưu lại cache
        services.save_cache("ipad")
        
    return {"status": "success", "message": f"Đã xóa ảnh {filename}"}


@router.post("/api/check-ip")
def check_client_ip(req_data: CheckIPRequest, db: Session = Depends(get_db)):
    user_id = req_data.user_id.upper()
    client_ip = req_data.client_public_ip  # Lấy IP từ Frontend gửi lên
    
    # --- 1. LẤY CẤU HÌNH NHÂN VIÊN TỪ DATABASE ---
    from models import Employee
    emp = db.query(Employee).filter(Employee.username == user_id).first()
    
    # Mặc định an toàn: Phải check mạng, check GPS, và cho phép CC Cá nhân
    needs_network = 1
    needs_gps = 1
    can_personal = 1
    
    if emp:
        # Nếu cột trong DB là None (null) thì mặc định là 1 (Bật)
        needs_network = 1 if getattr(emp, 'checkMang', 1) in [1, None] else 0
        needs_gps = 1 if getattr(emp, 'checkViTri', 1) in [1, None] else 0
        can_personal = 1 if getattr(emp, 'ccCaNhan', 1) in [1, None] else 0

    # --- 2. KIỂM TRA MẠNG (Chỉ kiểm tra lấy lệ để trả về trạng thái, Backend thực sự chặn ở verify-personal) ---
    allowed_ips_str = services.get_config("ALLOWED_ENROLL_IPS", "*")
    is_valid = False
    
    if allowed_ips_str.strip() == "*":
        is_valid = True
    else:
        allowed_ips = [ip.strip() for ip in allowed_ips_str.split(",") if ip.strip()]
        is_valid = any(client_ip.startswith(allowed) or client_ip == allowed for allowed in allowed_ips)
        
    return {
        "valid": is_valid,
        "ip": client_ip,
        "user_checked": user_id,
        "checkMang": needs_network,
        "checkViTri": needs_gps,
        "ccCaNhan": can_personal
    }

@router.post("/api/verify-personal")
async def verify_personal(request: Request, data: PersonalVerifyRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    user_id = data.user_id.upper()
    client_ip = data.client_public_ip
    request.state.user_id = user_id
    
    # --- 1. KIỂM TRA QUYỀN & CẤU HÌNH NHÂN VIÊN ---
    from models import Employee
    emp = db.query(Employee).filter(Employee.username == user_id).first()
    
    if not emp:
        return {"recognized": False, "message": "Không tìm thấy thông tin tài khoản."}
        
    # Kiểm tra quyền Chấm công cá nhân
    can_personal = 1 if getattr(emp, 'ccCaNhan', 1) in [1, None] else 0
    if can_personal == 0:
        return {"recognized": False, "message": "Tài khoản bị cấm chấm công cá nhân!"}
    
    # --- 2. KIỂM TRA MẠNG & VỊ TRÍ (LOGIC: 1 TRONG 2) ---
    needs_network = 1 if getattr(emp, 'checkMang', 1) in [1, None] else 0
    needs_gps = 1 if getattr(emp, 'checkViTri', 1) in [1, None] else 0
    
    is_network_valid = False
    is_location_valid = False

    # 2.1 Chấm điểm Mạng (IP)
    if needs_network == 0:
        is_network_valid = True
    else:
        allowed_ips_str = services.get_config("ALLOWED_ENROLL_IPS", "*") 
        if allowed_ips_str.strip() == "*":
            is_network_valid = True
        else:
            allowed_ips = [ip.strip() for ip in allowed_ips_str.split(",") if ip.strip()]
            is_network_valid = any(client_ip.startswith(allowed) or client_ip == allowed for allowed in allowed_ips)

    if needs_gps == 0:
        is_location_valid = True
    else:
        client_lat = data.latitude
        client_lng = data.longitude
        
        if client_lat and client_lng and client_lat != 0 and client_lng != 0:
            polygon = [
                (21.132651, 105.774238), (21.131013, 105.776601), 
                (21.130023, 105.773278), (21.130553, 105.772459)
            ]

            x, y = float(client_lng), float(client_lat)
            inside = False
            j = len(polygon) - 1
            for i in range(len(polygon)):
                xi, yi = polygon[i][1], polygon[i][0]
                xj, yj = polygon[j][1], polygon[j][0]
                intersect = ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi)
                if intersect:
                    inside = not inside
                j = i
            is_location_valid = inside

    if not is_network_valid and not is_location_valid:
        return {"recognized": False, "message": "Sai mạng Wi-Fi và Ngoài vị trí Bệnh viện!"}

    # --- 3. TIẾN HÀNH AI NHẬN DIỆN KHUÔN MẶT ---
    if user_id not in services.known_user_ids:
        return {"recognized": False, "message": "Bạn chưa đăng ký khuôn mặt!"}
        
    try:
        img_crop = services.decode_base64(data.image_base64)
        img_full = services.decode_base64(data.full_image_base64) if data.full_image_base64 else None
        is_anti_spoof_enabled = services.get_config("ENABLE_ANTI_SPOOFING", "true").lower() == "true"

        results = await run_in_threadpool(DeepFace.represent, img_path=img_crop, model_name=MODEL_NAME, enforce_detection=False, anti_spoofing=is_anti_spoof_enabled)
        if not results:
            return {"recognized": False, "message": "Không thấy mặt"}

        if is_anti_spoof_enabled and not results[0].get("is_real", True):
             return {"recognized": False, "message": "Phát hiện gian lận hình ảnh!"}

        current_embedding = np.array(results[0]["embedding"])

        user_indices = [i for i, uid in enumerate(services.known_user_ids) if uid == user_id]
        user_embeddings = services.known_embeddings_matrix[user_indices]
        
        dot_products = np.dot(user_embeddings, current_embedding)
        matrix_norms = np.linalg.norm(user_embeddings, axis=1)
        current_norm = np.linalg.norm(current_embedding)
        
        similarities = dot_products / (matrix_norms * current_norm)
        max_sim = np.max(similarities)
        
        THRESHOLD = float(services.get_config("FACE_THRESHOLD_PERSONAL", "0.75"))
        
        if max_sim >= THRESHOLD:
            background_tasks.add_task(services.background_logging, user_id, img_full, max_sim, client_ip,data.latitude,data.longitude,data.attendance_type,data.note)
            return {"recognized": True, "message": "Thành công", "match_probability": f"{round(max_sim * 100, 2)}%"}
        else:
            return {"recognized": False, "message": "⚠️ VUI LÒNG GIỮ THẲNG KHUÔN MẶT, VÀ GIỮ Ở GIỮA KHUNG HÌNH", "match_probability": f"{round(max_sim * 100, 2)}%"}

    except Exception as e:
        error_msg = str(e).lower()
        if "spoof detected" in error_msg:
            return {"recognized": False, "message": "CẢNH BÁO GIAN LẬN!"}
        elif "face could not be detected" in error_msg:
            return {"recognized": False, "message": "Không tìm thấy khuôn mặt"}
        else:
            return {"recognized": False, "message": f"Lỗi: {str(e)}"}
        

@router.post("/api/test-real-flow")
async def test_real_flow(request: TestFaceRequest):
    try:
        # Nhận ảnh ĐÃ CẮT từ Frontend
        img_crop = services.decode_base64(request.image_base64)
        
        # Chạy DeepFace với setting GIỐNG HỆT lúc chấm công thật
        results = await run_in_threadpool(
            DeepFace.represent, 
            img_path=img_crop, 
            model_name=MODEL_NAME, 
            enforce_detection=True, 
            detector_backend="skip", # Ép AI tin tưởng tuyệt đối vào ảnh crop
            anti_spoofing=False # Tắt kiểm tra Fake/Real để tập trung xem độ giống
        )
        
        if not results:
            return {"status": "error", "message": "Backend không thể trích xuất Vector từ bức ảnh này."}
            
        current_embedding = np.array(results[0]["embedding"])
        top_matches = []
        
        if len(services.known_user_ids) > 0:
            # So sánh ma trận Vector
            dot_products = np.dot(services.known_embeddings_matrix, current_embedding)
            matrix_norms = np.linalg.norm(services.known_embeddings_matrix, axis=1)
            current_norm = np.linalg.norm(current_embedding)
            
            similarities = dot_products / (matrix_norms * current_norm)
            
            # Lấy Top 3 người giống nhất
            top_3_indices = np.argsort(similarities)[-3:][::-1]
            for i in top_3_indices:
                top_matches.append({
                    "user_id": services.known_user_ids[i],
                    "similarity": round(float(similarities[i]) * 100, 2)
                })
                
        return {
            "status": "success",
            "message": "Phân tích Vector dựa trên ảnh Crop thành công",
            "top_3_matches": top_matches
        }
        
    except Exception as e:
        return {"status": "error", "message": f"Lỗi hệ thống: {str(e)}"}

@router.post("/api/admin/scan-fraud")
async def scan_fraud_records(req: ScanFraudRequest, db: Session = Depends(get_db)):
    try:
        print(f"\n🚀 --- BẮT ĐẦU CHIẾN DỊCH QUÉT GIAN LẬN CẤP ĐỘ CAO ---")
        start_dt = datetime.strptime(req.start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(req.end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
        
        records = db.query(Attendance).filter(
            Attendance.check_in_time >= start_dt,
            Attendance.check_in_time <= end_dt,
            Attendance.image_path != None,
            Attendance.image_path != ""
        ).all()

        total_records = len(records)
        if not records:
            return {"status": "success", "message": "Không có ảnh hợp lệ cần quét.", "scanned_count": 0, "scanned_filenames": [], "fraud_detected": 0, "fraud_list": []}

        fraud_count = 0
        total_files_on_disk_scanned = 0
        scanned_filenames = []
        fraud_list = []

        for index, record in enumerate(records, 1):
            db_path = record.image_path
            if not db_path: continue
            
            # Chuẩn hóa đường dẫn chống lỗi Windows/Linux
            clean_db_path = db_path.replace("\\", "/").lstrip(".").lstrip("/")
            physical_img_path = os.path.join(BASE_DIR, clean_db_path)
            filename = os.path.basename(physical_img_path)

            if filename.startswith("UNKNOWN"):
                continue

            if not os.path.exists(physical_img_path) or os.path.getsize(physical_img_path) < 1024:
                continue
                
            # ĐỌC ẢNH VÀO RAM CHỐNG LỖI FILE SIGNATURE
            try:
                img_array = np.fromfile(physical_img_path, np.uint8)
                img_data = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                if img_data is None: continue
            except Exception:
                continue

            print(f"[{index}/{total_records}] 🔍 Đang soi AI: {filename}...")
            total_files_on_disk_scanned += 1
            scanned_filenames.append(filename)
            
            is_fraud_detected = False
            fraud_reason = ""

            try:
                # --- VÒNG 1: YOLO QUÉT GÓC RỘNG VỚI ĐỘ NHẠY CỰC CAO (15%) ---
                yolo_results = object_model(img_data, verbose=False)
                # 62: TV/Monitor, 63: Laptop, 67: Cell phone, 73: Book (Dễ nhầm với mặt phẳng)
                suspicious_classes = [62, 63, 67, 73] 
                
                for r in yolo_results:
                    for box in r.boxes:
                        class_id = int(box.cls[0])
                        conf = float(box.conf[0])
                        # Chỉ cần AI thấy có 15% khả năng là thiết bị/mặt phẳng, tóm ngay!
                        if class_id in suspicious_classes and conf > 0.15: 
                            is_fraud_detected = True
                            class_name = r.names[class_id].upper()
                            fraud_reason = f"AI quét thấy vật thể lạ: {class_name} ({round(conf*100)}%)"
                            break
                    if is_fraud_detected: break

                # --- VÒNG 2: DEEPFACE SOI CẬN CẢNH MẶT PHẲNG ---
                if not is_fraud_detected:
                    faces = DeepFace.extract_faces(
                        img_path=img_data, 
                        detector_backend="retinaface",
                        enforce_detection=False, # Không văng lỗi nếu lỡ ảnh quá mờ
                        anti_spoofing=True,
                        expand_percentage=0 # <-- Khóa 0% để soi sát cấu trúc điểm ảnh da mặt, bỏ qua bối cảnh nhiễu
                    )
                    
                    if faces and not faces[0].get("is_real", True):
                        is_fraud_detected = True
                        fraud_reason = "Nghi vấn dùng ảnh in/mặt phẳng 2D (Fasnet AI)"

                # --- ĐÓNG GÓI KẾT QUẢ ---
                if is_fraud_detected:
                    print(f"   => 🚨 BẮT QUẢ TANG: {fraud_reason}")
                    record.is_fraud = True
                    record.fraud_note = fraud_reason
                    fraud_count += 1
                    
                    emp_name = record.employee.full_name if record.employee else "Unknown"
                    scan_time_str = str(record.scan_time) if record.scan_time else "N/A"
                    
                    fraud_list.append({
                        "name": emp_name,
                        "username": record.username,
                        "time": scan_time_str,
                        "filename": filename,
                        "image_path": record.image_path
                    })
                else:
                    print(f"   => ✅ Hợp lệ")
                    
            except Exception as e:
                print(f"   => ⚠️ Lỗi xử lý AI: {e}")
                continue
                
        if fraud_count > 0:
            db.commit()

        return {
            "status": "success", 
            "message": f"Đã quét thành công.",
            "scanned_count": total_files_on_disk_scanned,
            "scanned_filenames": scanned_filenames,
            "fraud_detected": fraud_count,
            "fraud_list": fraud_list
        }

    except Exception as e:
        print(f"🔥 LỖI CHÍ MẠNG TOÀN HỆ THỐNG: {e}")
        return {"status": "error", "message": f"Lỗi hệ thống khi quét: {str(e)}"}


@router.post("/api/confirm-renew")
async def confirm_renew(request: FaceRequest, background_tasks: BackgroundTasks):
    user_id = request.user_id.upper()
    img_crop = services.decode_base64(request.image_base64)
    img_full = services.decode_base64(request.full_image_base64) if request.full_image_base64 else img_crop
    
    # Ép lưu file thứ 4 để không đè lên 3 ảnh gốc của nhân sự
    new_filename = f"{user_id}_4.jpg"
    file_key = f"{user_id}_4"
    file_path = os.path.join(IPAD_FILE, new_filename)
    
    cv2.imwrite(file_path, img_crop)
    
    try:
        results = await run_in_threadpool(DeepFace.represent, img_path=img_crop, model_name=MODEL_NAME, enforce_detection=False)
        embedding = np.array(results[0]["embedding"])
        
        # 1. Đẩy thẳng vào RAM ngay lập tức
        if file_key in services.ipad_file_keys:
            idx = services.ipad_file_keys.index(file_key)
            services.ipad_embeddings_matrix[idx] = embedding
        else:
            services.ipad_file_keys.append(file_key)
            services.ipad_user_ids.append(user_id)
            if services.ipad_embeddings_matrix.size == 0:
                services.ipad_embeddings_matrix = np.array([embedding])
            else:
                services.ipad_embeddings_matrix = np.vstack([services.ipad_embeddings_matrix, embedding])
        
        if hasattr(services, 'save_cache'):
            services.save_cache()
            
        # 2. Ghi nhận Chấm công với Ghi chú "renew"
        background_tasks.add_task(
            services.background_logging, 
            user_id, 
            img_full, 
            1.0, # Độ tin cậy ép lên 100% vì đã được người dùng xác nhận
            request.client_public_ip, 
            0, 0, 
            request.attendance_type, 
            "renew"
        )
        
        return {"status": "success", "message": f"Đã cập nhật AI và chấm công cho {user_id}"}
        
    except Exception as e:
        if os.path.exists(file_path): os.remove(file_path)
        return {"status": "error", "message": f"Lỗi cập nhật AI: {e}"}


# --- API 1: TRẢ VỀ TOÀN BỘ ẢNH CỦA 1 NHÂN VIÊN (Base64) ---
@router.get("/api/user-faces/{user_id}")
async def get_user_faces_for_local(user_id: str):
    user_id = user_id.upper()
    images = []
    # Tìm tối đa 5 ảnh của người này
    possible_files = [f"{user_id}.jpg", f"{user_id}_1.jpg", f"{user_id}_2.jpg", f"{user_id}_3.jpg", f"{user_id}_4.jpg"]
    
    for pf in possible_files:
        file_path = os.path.join(DB_PATH, pf)
        if os.path.exists(file_path):
            with open(file_path, "rb") as f:
                encoded = base64.b64encode(f.read()).decode('utf-8')
                images.append(encoded)
    
    if not images:
        return {"status": "error", "message": "Tài khoản chưa có ảnh đăng ký"}
    return {"status": "success", "images": images}


# --- API 2: GHI NHẬN CHẤM CÔNG (BỎ QUA DEEPFACE SO KHỚP) ---
@router.post("/api/log-local-attendance")
async def log_local_attendance(data: dict, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    user_id = data.get("user_id").upper()
    img_full_base64 = data.get("full_image_base64")
    client_ip = data.get("client_public_ip")
    lat = data.get("latitude", 0)
    lng = data.get("longitude", 0)
    att_type = data.get("attendance_type", "Cá nhân v3")
    note = data.get("note", "Local Match")
    match_probability = data.get("match_probability", 1.0)  # Mặc định 100% nếu Frontend đã xác nhận

    try:
        # Giải mã ảnh để lưu vào ổ cứng
        img_full = services.decode_base64(img_full_base64) if img_full_base64 else None
        
        # Bỏ qua khâu AI DeepFace, gọi thẳng hàm background_logging để ghi DB
        background_tasks.add_task(
            services.background_logging, 
            user_id, 
            img_full, 
            match_probability,
            client_ip, 
            lat, 
            lng, 
            att_type, 
            note
        )
        return {"status": "success", "message": "Chấm công thành công"}
    except Exception as e:
        return {"status": "error", "message": f"Lỗi ghi nhận: {str(e)}"}