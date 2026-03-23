import os
import cv2
import glob
import numpy as np
from fastapi.responses import FileResponse
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from fastapi.concurrency import run_in_threadpool
from deepface import DeepFace
from sqlalchemy.orm import Session
from schemas import CheckIPRequest, FaceRequest, SingleFaceDeleteRequest, UnregisterRequest, PersonalVerifyRequest, TestFaceRequest, UpdateImageUrlRequest
from config import DB_PATH, MODEL_NAME, CACHE_FILE
from database import get_db

import services 

router = APIRouter()

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

    img_crop = services.decode_base64(request.image_base64)
    img_to_save = services.decode_base64(request.full_image_base64) if request.full_image_base64 else img_crop
    max_sim = 0.0
    is_anti_spoof_enabled = services.get_config("ENABLE_ANTI_SPOOFING", "true").lower() == "true"

    try:
        
        results = await run_in_threadpool(DeepFace.represent, img_path=img_crop, model_name=MODEL_NAME, enforce_detection=True,detector_backend="skip",anti_spoofing=is_anti_spoof_enabled)
        if not results: return {"recognized": False, "message": "Không thấy mặt"}
        
        if is_anti_spoof_enabled and not results[0].get("is_real", True):
             return {"recognized": False, "message": "Phát hiện gian lận hình ảnh!"}

        
        current_embedding = np.array(results[0]["embedding"])
        
        if len(services.known_user_ids) == 0:
            return {"recognized": False, "message": "RAM chưa có dữ liệu, hãy tải lại."}

        dot_products = np.dot(services.known_embeddings_matrix, current_embedding)
        matrix_norms = np.linalg.norm(services.known_embeddings_matrix, axis=1)
        current_norm = np.linalg.norm(current_embedding)
        
        similarities = dot_products / (matrix_norms * current_norm)
        
        sorted_indices = np.argsort(similarities)[::-1]
        
        best_index = sorted_indices[0]
        max_sim = similarities[best_index]
        best_match = services.known_user_ids[best_index]
        
        # Tìm người giống thứ 2 (Top 2 - Bắt buộc phải KHÁC Mã nhân viên với Top 1)
        second_best_sim = 0.0
        second_best_match = None
        
        for idx in sorted_indices[1:]:
            if services.known_user_ids[idx] != best_match:
                second_best_sim = similarities[idx]
                second_best_match = services.known_user_ids[idx]
                break 
                
        # Tính khoảng cách tự tin (Margin) quy ra phần trăm
        margin_percent = (max_sim - second_best_sim) * 100
        
        THRESHOLD = float(services.get_config("FACE_THRESHOLD", "0.75"))

        if max_sim >= THRESHOLD:
            if second_best_match and margin_percent < 4.0:
                # Lưu vào DB lịch sử bị từ chối do nhiễu
                note_str = f"Từ chối do quá giống {second_best_match} (Lệch {round(margin_percent, 2)}% < 4%)"
                background_tasks.add_task(services.background_logging, "UNKNOWN", img_to_save, max_sim, request.client_public_ip, 0, 0, request.attendance_type, note_str)
                
                return {
                    "recognized": False, 
                    "message": f"⚠️ GÓC CHỤP BỊ NHIỄU, VUI LÒNG THỬ LẠI", 
                    "match_probability": f"{round(max_sim * 100, 2)}%"
                }

            # Qua mượt cả Threshold lẫn Margin -> Chấm công thành công!
            background_tasks.add_task(services.background_logging, best_match, img_to_save, max_sim, request.client_public_ip, 0, 0, request.attendance_type, '')
            return {"recognized": True, "user_id": best_match, "match_probability": f"{round(max_sim * 100, 2)}%"}
        
        # Trường hợp không đủ Threshold (như cũ)
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

@router.get("/clear_ram")
async def clear_ram():
    services.known_file_keys.clear()
    services.known_user_ids.clear()
    services.known_embeddings_matrix = np.array([])
    if os.path.exists(CACHE_FILE): os.remove(CACHE_FILE)
    return {"status": "success"}

@router.get("/api/ai_status")
async def get_ai_status():
    import os
    files = [f for f in os.listdir(DB_PATH) if f.endswith(".jpg")]
    
    return {
        "files_count": len(files), 
        "ram_count": len(services.known_file_keys)
    }

@router.get("/reload_ram")
async def reload_ram_api():
    services.load_embeddings()
    return {
        "status": "success", 
        "message": f"Đã nạp lại {len(services.known_file_keys)} khuôn mặt vào RAM!"
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
        services.save_cache()
        
    return {"status": "success", "message": f"Đã xóa ảnh {filename}"}


@router.post("/api/check-ip")
def check_client_ip(req_data: CheckIPRequest):
    user_id = req_data.user_id.upper()
    client_ip = req_data.client_public_ip  # Lấy IP từ Frontend gửi lên
    
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
        "user_checked": user_id
    }

@router.post("/api/verify-personal")
async def verify_personal(data: PersonalVerifyRequest, background_tasks: BackgroundTasks):
    user_id = data.user_id.upper()
    client_ip = data.client_public_ip
    
    allowed_ips_str = services.get_config("ALLOWED_ENROLL_IPS", "*") 
    if allowed_ips_str.strip() != "*":
        allowed_ips = [ip.strip() for ip in allowed_ips_str.split(",") if ip.strip()]
        if not any(client_ip.startswith(allowed) or client_ip == allowed for allowed in allowed_ips):
            return {"recognized": False, "message": "Sai địa chỉ IP/Mạng lưới Bệnh viện."}

    if user_id not in services.known_user_ids:
        return {"recognized": False, "message": "Bạn chưa đăng ký khuôn mặt!"}
        
    try:
        img_crop = services.decode_base64(data.image_base64)
        img_full = services.decode_base64(data.full_image_base64) if data.full_image_base64 else None
        is_anti_spoof_enabled = services.get_config("ENABLE_ANTI_SPOOFING", "true").lower() == "true"

        results = await run_in_threadpool(
            DeepFace.represent, 
            img_path=img_crop, 
            model_name=MODEL_NAME, 
            enforce_detection=False, 
            anti_spoofing=is_anti_spoof_enabled
        )
        
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

            return {
                "recognized": True, 
                "message": "Thành công", 
                "match_probability": f"{round(max_sim * 100, 2)}%"
            }
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