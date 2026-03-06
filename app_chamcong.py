import cv2
import time
import base64
import requests
import threading
import mediapipe as mp

# Gọi thẳng vào API recognize (Không cần gửi USER_ID)
API_URL = "http://localhost:8000/recognize"

# Biến trạng thái
is_processing = False
api_result = None
last_verify_time = 0

def call_api(b64_img):
    global api_result, is_processing, last_verify_time
    try:
        # Payload chỉ gửi mỗi bức ảnh lên máy chủ
        response = requests.post(API_URL, json={
            "image_base64": b64_img
        })
        if response.status_code == 200:
            api_result = response.json()
        else:
            api_result = {"recognized": False, "message": f"Lỗi Server: {response.status_code}"}
    except Exception as e:
        api_result = {"recognized": False, "message": "Lỗi kết nối Server"}
    
    is_processing = False
    last_verify_time = time.time()

# Khởi tạo Camera
cap = cv2.VideoCapture(0)
mp_face_detection = mp.solutions.face_detection
face_detector = mp_face_detection.FaceDetection(min_detection_confidence=0.7)

print("Đang mở Camera chấm công...")

while cap.isOpened():
    ret, frame = cap.read()
    if not ret: break
    
    frame = cv2.flip(frame, 1) # Lật gương
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    
    # 1. Tìm khuôn mặt trong khung hình
    results = face_detector.process(rgb_frame)
    
    if results.detections:
        for detection in results.detections:
            bboxC = detection.location_data.relative_bounding_box
            ih, iw, _ = frame.shape
            x, y, w, h = int(bboxC.xmin * iw), int(bboxC.ymin * ih), int(bboxC.width * iw), int(bboxC.height * ih)
            
            # Vẽ khung xanh lá
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
            
            # 2. Nếu đã nghỉ đủ 3 giây, tự động chụp và gửi ảnh
            if not is_processing and (time.time() - last_verify_time > 3):
                _, buffer = cv2.imencode('.jpg', frame)
                b64_img = base64.b64encode(buffer).decode('utf-8')
                
                is_processing = True
                api_result = None
                
                # Gọi API chạy ngầm
                threading.Thread(target=call_api, args=(b64_img,)).start()

    # 3. Hiển thị chữ trạng thái xử lý
    if is_processing:
        cv2.putText(frame, "Dang nhan dien...", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 165, 255), 2)
        
    # 4. Hiển thị kết quả AI (Hiện trong 3 giây)
    # Hiển thị kết quả trong vòng 3 giây
    if api_result and (time.time() - last_verify_time < 3):
        prob = api_result.get("match_probability", "0%")
        
        if api_result.get("recognized"):
            uid = api_result.get("user_id")
            msg = f"{uid} - Khop: {prob}"
            color = (0, 255, 0) # Xanh lá
        else:
            reason = api_result.get("message", "Nguoi la")
            msg = f"{reason} ({prob})"
            color = (0, 0, 255) # Đỏ
            
        cv2.putText(frame, msg, (20, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

    cv2.imshow("He Thong Cham Cong Tu Dong (1:N)", frame)
    
    if cv2.waitKey(1) & 0xFF == ord('q'): break

cap.release()
cv2.destroyAllWindows()