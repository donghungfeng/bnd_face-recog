from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from datetime import datetime, date
import openpyxl
import io
from openpyxl.styles import Font, PatternFill
from sqlalchemy.orm import joinedload # Nhớ import hàm này ở đầu file nếu chưa có

from fastapi.templating import Jinja2Templates
templates = Jinja2Templates(directory="templates")

from database import get_db
from models import ShiftCategory, ShiftAssignment, Employee
from schemas import ShiftCategoryCreate, ShiftAssignmentCreate

router = APIRouter()

@router.get("/assignments")
def read_assignments(request: Request): 
    return templates.TemplateResponse("assignments.html", {"request": request})

# ==========================================
# 1. API DANH MỤC CA TRỰC
# ==========================================
@router.post("/api/shifts")
def create_shift_category(shift: ShiftCategoryCreate, db: Session = Depends(get_db)):
    db_shift = db.query(ShiftCategory).filter(ShiftCategory.shift_code == shift.shift_code).first()
    if db_shift:
        raise HTTPException(status_code=400, detail="Mã ca trực đã tồn tại")
    
    new_shift = ShiftCategory(**shift.dict())
    db.add(new_shift)
    db.commit()
    return {"status": "success", "message": "Thêm ca trực thành công"}

@router.get("/api/shifts")
def get_shifts(db: Session = Depends(get_db)):
    return db.query(ShiftCategory).all()

@router.delete("/api/shifts/{shift_code}")
def delete_shift(shift_code: str, db: Session = Depends(get_db)):
    shift = db.query(ShiftCategory).filter(ShiftCategory.shift_code == shift_code).first()
    if not shift: 
        raise HTTPException(status_code=404, detail="Không tìm thấy ca trực")
    db.delete(shift)
    db.commit()
    return {"status": "success"}


# ==========================================
# 2. API PHÂN CÔNG CA TRỰC & EXCEL
# ==========================================
@router.get("/api/assignments")
def get_assignments(month: int, year: int, db: Session = Depends(get_db)):
    start_date = date(year, month, 1)
    if month == 12: 
        end_date = date(year + 1, 1, 1)
    else: 
        end_date = date(year, month + 1, 1)

    assignments = db.query(ShiftAssignment, Employee.full_name, ShiftCategory.shift_name).join(
        Employee, ShiftAssignment.username == Employee.username
    ).join(
        ShiftCategory, ShiftAssignment.shift_code == ShiftCategory.shift_code
    ).filter(
        ShiftAssignment.shift_date >= start_date,
        ShiftAssignment.shift_date < end_date
    ).all()

    return [{
        "id": a[0].id, 
        "username": a[0].username, 
        "full_name": a[1],
        "shift_code": a[0].shift_code, 
        "shift_name": a[2], 
        "shift_date": a[0].shift_date,
        "assigner": a[0].assigner  # <--- BỔ SUNG DÒNG NÀY VÀO ĐỂ TRẢ VỀ UI
    } for a in assignments]

@router.post("/api/assignments")
def create_assignment(req: ShiftAssignmentCreate, db: Session = Depends(get_db)):
    existing = db.query(ShiftAssignment).filter(
        ShiftAssignment.username == req.username, 
        ShiftAssignment.shift_date == req.shift_date
    ).first()
    
    if existing:
        existing.shift_code = req.shift_code # Ghi đè nếu đã có lịch ngày đó
    else:
        db.add(ShiftAssignment(**req.dict()))
    db.commit()
    return {"status": "success"}

@router.delete("/api/assignments/{assign_id}")
def delete_assignment(assign_id: int, db: Session = Depends(get_db)):
    item = db.query(ShiftAssignment).filter(ShiftAssignment.id == assign_id).first()
    if item:
        db.delete(item)
        db.commit()
    return {"status": "success"}


# ==========================================
# 3. IMPORT / EXPORT EXCEL PHÂN CÔNG
# ==========================================
@router.get("/api/assignments/export_template")
def export_assignment_template(db: Session = Depends(get_db)):
    wb = openpyxl.Workbook()
    
    # ==========================================
    # SHEET 1: BẢNG PHÂN CÔNG CA TRỰC
    # ==========================================
    ws1 = wb.active
    ws1.title = "PhanCongCaTruc"
    
    headers1 = [
        "MÃ NHÂN VIÊN", 
        "TÊN NHÂN VIÊN", 
        "ĐƠN VỊ", 
        "MÃ CA TRỰC", 
        "NGÀY TRỰC (YYYY-MM-DD)", 
        "MÃ NGƯỜI GIAO",
        "TÊN NGƯỜI GIAO"
    ]
    ws1.append(headers1)
    
    # Format Header Sheet 1 (Màu xanh dương)
    header_font = Font(bold=True, color="FFFFFF")
    for cell in ws1[1]:
        cell.font = header_font
        cell.fill = PatternFill(start_color="4361EE", fill_type="solid")
    
    ws1.column_dimensions['A'].width = 15
    ws1.column_dimensions['B'].width = 25
    ws1.column_dimensions['C'].width = 30
    ws1.column_dimensions['D'].width = 25
    ws1.column_dimensions['E'].width = 25
    ws1.column_dimensions['F'].width = 18
    ws1.column_dimensions['G'].width = 25

    # Đổ danh sách nhân viên vào Sheet 1
    emps = db.query(Employee).options(joinedload(Employee.department)).filter(Employee.status == 'active').all()
    for emp in emps:
        dept_name = emp.department.unit_name if emp.department else ""
        ws1.append([emp.username, emp.full_name, dept_name, "", "", "", ""])


    # ==========================================
    # SHEET 2: DANH MỤC CA TRỰC (Để người dùng tra cứu)
    # ==========================================
    ws2 = wb.create_sheet(title="DanhMucCaTruc")
    headers2 = ["MÃ CA TRỰC", "TÊN CA TRỰC", "GIỜ BẮT ĐẦU", "GIỜ KẾT THÚC", "LOẠI CA", "GHI CHÚ"]
    ws2.append(headers2)

    # Format Header Sheet 2 (Màu xanh lá ngọc cho dễ phân biệt)
    for cell in ws2[1]:
        cell.font = header_font
        cell.fill = PatternFill(start_color="10B981", fill_type="solid")
        
    ws2.column_dimensions['A'].width = 20
    ws2.column_dimensions['B'].width = 30
    ws2.column_dimensions['C'].width = 15
    ws2.column_dimensions['D'].width = 15
    ws2.column_dimensions['E'].width = 20
    ws2.column_dimensions['F'].width = 35

    # Đổ danh sách Ca trực vào Sheet 2
    shifts = db.query(ShiftCategory).all()
    for s in shifts:
        shift_type = "🌙 Qua ngày" if s.is_overnight == 1 else "☀️ Trong ngày"
        start_str = s.start_time.strftime("%H:%M") if s.start_time else ""
        end_str = s.end_time.strftime("%H:%M") if s.end_time else ""
        
        ws2.append([s.shift_code, s.shift_name, start_str, end_str, shift_type, s.notes or ""])

    # Lưu và trả về file Excel
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    
    return StreamingResponse(
        output, 
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", 
        headers={"Content-Disposition": "attachment; filename=Mau_Import_Ca_Truc.xlsx"}
    )

@router.post("/api/assignments/import")
async def import_assignments(file: UploadFile = File(...), db: Session = Depends(get_db)):
    try:
        contents = await file.read()
        wb = openpyxl.load_workbook(filename=io.BytesIO(contents))
        
        # Chỉ định rõ đọc dữ liệu từ Sheet "PhanCongCaTruc"
        if "PhanCongCaTruc" not in wb.sheetnames:
            raise HTTPException(status_code=400, detail="File Excel không đúng định dạng mẫu (Thiếu sheet PhanCongCaTruc).")
            
        ws = wb["PhanCongCaTruc"]
        count = 0
        
        for row in ws.iter_rows(min_row=2, values_only=True):
            # Cột 0: Mã NV, Cột 3: Mã Ca, Cột 4: Ngày trực
            if not row[0] or not row[3] or not row[4]: 
                continue
            
            username = str(row[0]).strip()
            shift_code = str(row[3]).strip()
            
            # Xử lý Ngày trực
            shift_date_val = row[4]
            if isinstance(shift_date_val, datetime):
                shift_date = shift_date_val.date()
            else:
                try: 
                    shift_date = datetime.strptime(str(shift_date_val)[:10], "%Y-%m-%d").date()
                except ValueError: 
                    continue

            # Xử lý Người giao (Cột 5: Mã, Cột 6: Tên)
            assigner_code = str(row[5]).strip() if row[5] else ""
            assigner_name = str(row[6]).strip() if row[6] else ""
            
            # Ghép lại thành "Mã - Tên" (VD: NV01 - Nguyễn Văn A) để lưu vào 1 cột cho gọn
            assigner_full = ""
            if assigner_code and assigner_name:
                assigner_full = f"{assigner_code} - {assigner_name}"
            elif assigner_code or assigner_name:
                assigner_full = assigner_code or assigner_name
            else:
                assigner_full = None

            # Ghi đè vào CSDL nếu đã có ca trực vào ngày đó
            existing = db.query(ShiftAssignment).filter(
                ShiftAssignment.username == username, 
                ShiftAssignment.shift_date == shift_date
            ).first()
            
            if existing: 
                existing.shift_code = shift_code
                if assigner_full: existing.assigner = assigner_full
            else: 
                db.add(ShiftAssignment(
                    username=username, 
                    shift_code=shift_code, 
                    shift_date=shift_date,
                    assigner=assigner_full
                ))
            
            count += 1
            
        db.commit()
        return {"status": "success", "message": f"Đã import thành công {count} phân công ca trực!"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Lỗi đọc file Excel: {str(e)}")

@router.post("/api/assignments/import")
async def import_assignments(file: UploadFile = File(...), db: Session = Depends(get_db)):
    try:
        contents = await file.read()
        wb = openpyxl.load_workbook(filename=io.BytesIO(contents))
        ws = wb.active
        count = 0
        
        # Bắt đầu đọc từ dòng thứ 2 (bỏ qua Header)
        for row in ws.iter_rows(min_row=2, values_only=True):
            if not row[0] or not row[1] or not row[2]: 
                continue
            
            username = str(row[0]).strip()
            shift_code = str(row[1]).strip()
            
            # Xử lý ngày tháng an toàn (Excel có thể format là chuỗi hoặc datetime)
            shift_date_val = row[2]
            if isinstance(shift_date_val, datetime):
                shift_date = shift_date_val.date()
            else:
                try: 
                    shift_date = datetime.strptime(str(shift_date_val)[:10], "%Y-%m-%d").date()
                except ValueError: 
                    continue

            # Ghi đè nếu trùng ngày
            existing = db.query(ShiftAssignment).filter(
                ShiftAssignment.username == username, 
                ShiftAssignment.shift_date == shift_date
            ).first()
            
            if existing: 
                existing.shift_code = shift_code
            else: 
                db.add(ShiftAssignment(username=username, shift_code=shift_code, shift_date=shift_date))
            
            count += 1
            
        db.commit()
        return {"status": "success", "message": f"Đã import thành công {count} phân công!"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Lỗi đọc file: {str(e)}")