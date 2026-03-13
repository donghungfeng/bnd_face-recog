from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import AppConfig
from schemas import ConfigUpsertRequest
import services

router = APIRouter(prefix="/api/configs", tags=["System Configs"])

@router.get("/")
def get_all_configs(db: Session = Depends(get_db)):
    return db.query(AppConfig).all()

@router.post("/")
def update_config(req: ConfigUpsertRequest, db: Session = Depends(get_db)):
    # Tìm xem config này có trong DB chưa
    db_config = db.query(AppConfig).filter(AppConfig.config_key == req.config_key).first()
    
    if db_config:
        # Nếu có rồi thì cập nhật
        db_config.config_value = req.config_value
        db_config.description = req.description
    else:
        # Nếu chưa có thì tạo mới
        db_config = AppConfig(
            config_key=req.config_key,
            config_value=req.config_value,
            description=req.description
        )
        db.add(db_config)
        
    db.commit()
    
    # QUAN TRỌNG NHẤT: Cập nhật luôn biến RAM để AI áp dụng ngay lặp tức!
    services.sys_configs[req.config_key] = req.config_value
    
    return {"status": "success", "message": f"Đã lưu cấu hình {req.config_key}"}

@router.delete("/{config_key}")
def delete_config(config_key: str, db: Session = Depends(get_db)):
    # Tìm cấu hình trong DB
    db_config = db.query(AppConfig).filter(AppConfig.config_key == config_key).first()
    
    if not db_config:
        raise HTTPException(status_code=404, detail="Không tìm thấy cấu hình này")
        
    # Xóa khỏi Database
    db.delete(db_config)
    db.commit()
    
    # QUAN TRỌNG: Xóa luôn khỏi RAM để AI ngừng sử dụng biến này
    if config_key in services.sys_configs:
        del services.sys_configs[config_key]
        
    return {"status": "success", "message": f"Đã xóa cấu hình {config_key}"}