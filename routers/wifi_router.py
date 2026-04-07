from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

import models
import schemas
from database import get_db
# Giả sử bạn có hàm get_current_user để lấy user đang đăng nhập từ auth
from routers.auth_router import get_current_user

router = APIRouter(
    prefix="/api/wifi",
    tags=["Wifi"]
)

# Hàm hỗ trợ kiểm tra quyền Admin
def check_admin_role(user: models.Employee):
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Truy cập bị từ chối. Chỉ Admin mới có quyền thực hiện thao tác này."
        )

# 1. READ: Lấy danh sách Wifi
@router.get("/", response_model=List[schemas.WifiResponse])
def get_all_wifis(
    db: Session = Depends(get_db),
    current_user: models.Employee = Depends(get_current_user)
):
    # check_admin_role(current_user)
    
    wifis = db.query(models.Wifi).all()
    return wifis

# 2. CREATE: Thêm mới Wifi
@router.post("/", response_model=schemas.WifiResponse, status_code=status.HTTP_201_CREATED)
def create_wifi(
    wifi_data: schemas.WifiCreate,
    db: Session = Depends(get_db),
    current_user: models.Employee = Depends(get_current_user)
):
    # check_admin_role(current_user)
    
    new_wifi = models.Wifi(**wifi_data.model_dump())
    db.add(new_wifi)
    db.commit()
    db.refresh(new_wifi)
    return new_wifi

# 3. UPDATE: Cập nhật thông tin Wifi
@router.put("/{wifi_id}", response_model=schemas.WifiResponse)
def update_wifi(
    wifi_id: int,
    wifi_data: schemas.WifiUpdate,
    db: Session = Depends(get_db),
    current_user: models.Employee = Depends(get_current_user)
):
    # check_admin_role(current_user)
    
    wifi = db.query(models.Wifi).filter(models.Wifi.id == wifi_id).first()
    if not wifi:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy Wifi")

    # Cập nhật các trường có gửi lên (loại bỏ giá trị None)
    update_data = wifi_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(wifi, key, value)

    db.commit()
    db.refresh(wifi)
    return wifi

# 4. DELETE: Xóa Wifi
@router.delete("/{wifi_id}")
def delete_wifi(
    wifi_id: int,
    db: Session = Depends(get_db),
    current_user: models.Employee = Depends(get_current_user)
):
    # check_admin_role(current_user)
    
    wifi = db.query(models.Wifi).filter(models.Wifi.id == wifi_id).first()
    if not wifi:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy Wifi")

    db.delete(wifi)
    db.commit()
    return {"message": f"Đã xóa thành công Wifi ID {wifi_id}"}