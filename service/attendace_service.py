from datetime import time,date,datetime, timedelta
from collections import defaultdict
from enum import IntEnum
from typing import Optional
from sqlalchemy.orm import Session
import models, schemas, constants

def process_attendance_to_monthly(db, list_data):
    monthlyRecords = group_attendance_to_summaries(db, list_data)
    result = generate_monthly_records(db, monthlyRecords)
    return result

def group_attendance_to_summaries(db: Session, attendance_list: list[models.Attendance]) -> list[schemas.AttendanceSummary]:
    # 1. Tạo bản đồ cache để lấy employee_id từ username nhanh (tránh query liên tục)
    # Lấy danh sách username duy nhất từ list attendance
    unique_usernames = list(set(a.username for a in attendance_list))
    employee_map = {
        e.username: e.id 
        for e in db.query(models.Employee.id, models.Employee.username)
                 .filter(models.Employee.username.in_(unique_usernames)).all()
    }

    # 2. Dùng dictionary để gom nhóm: Key là (employee_id, date)
    # defaultdict(list) giúp tự tạo list mới nếu key chưa tồn tại
    grouped_data = defaultdict(list)

    for att in attendance_list:
        emp_id = employee_map.get(att.username)
        if not emp_id:
            continue # Bỏ qua nếu không tìm thấy nhân viên trong DB
        
        # Lấy phần ngày từ check_in_time (DateTime)
        att_date = att.check_in_time.date()
        
        # Tạo key duy nhất cho mỗi nhân viên trong mỗi ngày
        key = (emp_id, att.username, att_date)
        grouped_data[key].append(att)

    # 3. Chuyển dictionary thành list các object AttendanceSummary
    summaries = []
    for (emp_id, uname, target_date), scans in grouped_data.items():
        # Sắp xếp các lần quét trong ngày theo thời gian tăng dần
        scans.sort(key=lambda x: x.check_in_time)
        
        summaries.append(schemas.AttendanceSummary(
            employee_id=emp_id,
            username=uname,
            target_date=target_date,
            scans=scans
        ))

    return summaries

def calculate_shift_details(shift_cat, summary, next_day_summary=None):
    c_in = None
    c_out = None
    img_in = None
    img_out = None
    status = constants.AttendanceStatus.ABSENT
    late_min = 0
    early_min = 0
    
    # Khởi tạo giá trị mặc định cho logic mới
    actual_hours = 0.0
    actual_workday = 0.0

    if not summary or not summary.scans:
        return c_in, c_out, status, late_min, early_min, img_in, img_out, actual_hours, actual_workday

    # --- 1. XÁC ĐỊNH GIỜ VÀO & ẢNH VÀO (Giữ nguyên) ---
    first_scan = summary.scans[0]
    dt_in = first_scan.check_in_time
    c_in = dt_in.time()
    img_in = getattr(first_scan, 'image_path', None) 

    if shift_cat:
        ref_checkin_to = datetime.combine(summary.target_date, shift_cat.checkin_to)
        if dt_in > ref_checkin_to:
            late_min = int((dt_in - ref_checkin_to).total_seconds() / 60)

    # --- 2. XÁC ĐỊNH GIỜ RA & ẢNH RA (Giữ nguyên) ---
    dt_out = None
    now = datetime.now()
    
    ref_date_out = summary.target_date + timedelta(days=1) if (shift_cat and shift_cat.shift_code == "T") else summary.target_date
    end_time_limit = shift_cat.checkout_from if shift_cat else time(23, 59)
    ref_checkout_limit = datetime.combine(ref_date_out, end_time_limit)

    if shift_cat and shift_cat.shift_code == "T":
        if next_day_summary and next_day_summary.scans:
            last_scan = next_day_summary.scans[-1]
            dt_out = last_scan.check_in_time
    else:
        if len(summary.scans) > 1:
            last_scan = summary.scans[-1]
            dt_out = last_scan.check_in_time

    if dt_out is None and now >= ref_checkout_limit:
        dt_out = dt_in 
        
    if dt_out:
        c_out = dt_out.time()
        if dt_out == dt_in:
            img_out = img_in
        else:
            img_out = getattr(last_scan, 'image_path', None) if 'last_scan' in locals() else img_in

    # --- 3. PHÂN LOẠI TRẠNG THÁI (Giữ nguyên logic xác định status) ---
    if dt_out is None and now < ref_checkout_limit:
        status = constants.AttendanceStatus.LATE if late_min > 0 else constants.AttendanceStatus.IN_PROGRESS
        # Nếu đang trong quá trình làm việc, chưa tính công
        return c_in, None, status, late_min, 0, img_in, None, 0.0, 0.0

    if not shift_cat:
        # Không có ca định nghĩa thì mặc định PRESENT nhưng không có công chuẩn
        return c_in, c_out, constants.AttendanceStatus.PRESENT, 0, 0, img_in, img_out, 0.0, 0.0

    ref_checkout_from = datetime.combine(ref_date_out, shift_cat.checkout_from)
    if dt_out:
        if dt_out < ref_checkout_from:
            early_min = int((ref_checkout_from - dt_out).total_seconds() / 60)
        
        if late_min > 0 and early_min > 0:
            status = constants.AttendanceStatus.LATE_AND_EARLY_LEAVE
        elif late_min > 0:
            status = constants.AttendanceStatus.LATE
        elif early_min > 0:
            status = constants.AttendanceStatus.EARLY_LEAVE
        else:
            status = constants.AttendanceStatus.PRESENT
    else:
        status = constants.AttendanceStatus.ABSENT

    # --- 4. LOGIC MỚI: TÍNH TOÁN CÔNG THỰC TẾ (Chỉ check 4h cho status Vừa muộn vừa sớm) ---
    base_h = float(getattr(shift_cat, 'work_hours', 0.0))
    base_d = float(getattr(shift_cat, 'work_days', 0.0))

    # 1. Logic PRESENT (Đúng giờ) -> Full công
    if status == constants.AttendanceStatus.PRESENT:
        actual_hours = base_h
        actual_workday = base_d
    
    # 2. Logic LATE (2) hoặc EARLY_LEAVE (3) -> Luôn lấy nửa công (không check giờ)
    elif status in [constants.AttendanceStatus.LATE, constants.AttendanceStatus.EARLY_LEAVE]:
        actual_hours = base_h / 2
        actual_workday = base_d / 2
        
    # 3. Logic LATE_AND_EARLY_LEAVE (6) -> Check điều kiện 4 tiếng
    elif status == constants.AttendanceStatus.LATE_AND_EARLY_LEAVE:
        # Tính thời gian ở lại thực tế (giờ)
        work_duration_hours = 0.0
        if dt_in and dt_out:
            work_duration_hours = (dt_out - dt_in).total_seconds() / 3600

        if work_duration_hours < 4.0:
            actual_hours = 0.0
            actual_workday = 0.0
        else:
            # Nếu vi phạm cả hai nhưng vẫn ở lại trên 4 tiếng thì tính nửa công
            actual_hours = base_h / 2
            actual_workday = base_d / 2
            
    # 4. Logic mặc định (Vắng mặt / Đang làm việc)
    else:
        actual_hours = 0.0
        actual_workday = 0.0

    return c_in, c_out, status, late_min, early_min, img_in, img_out, actual_hours, actual_workday

def generate_monthly_records(db: Session, summary_list: list[schemas.AttendanceSummary]):
    if not summary_list:
        return []

    # 1. TỐI ƯU: Cache dữ liệu bảng ShiftAssignment và ShiftCategory
    emp_ids = list(set(s.employee_id for s in summary_list))
    dates = list(set(s.target_date for s in summary_list))
    
    # Truy vấn tất cả phân ca trong khoảng và lân cận để check ca T
    assignments = db.query(models.ShiftAssignment).filter(
        models.ShiftAssignment.employee_id.in_(emp_ids),
        models.ShiftAssignment.shift_date.in_(dates + [d - timedelta(days=1) for d in dates])
    ).all()
    assign_map = {(a.employee_id, a.shift_date): a.shift_code for a in assignments}

    categories = db.query(models.ShiftCategory).all()
    cat_map = {c.shift_code: c for c in categories}
    
    result_records = []
    summary_list.sort(key=lambda x: (x.employee_id, x.target_date))

    for i, summary in enumerate(summary_list):
        # --- BƯỚC QUAN TRỌNG: KIỂM TRA NGÀY HÔM TRƯỚC ---
        prev_date = summary.target_date - timedelta(days=1)
        prev_shift_code = assign_map.get((summary.employee_id, prev_date))
        
        # Nếu hôm trước làm ca T, thì ngày hôm nay là ngày "ra ca". 
        # Chúng ta bỏ qua không tạo dòng mới cho ngày hôm nay.
        if prev_shift_code == "T":
            continue 

        # Lấy mã ca hiện tại
        shift_code = assign_map.get((summary.employee_id, summary.target_date), "X")
        shift_cat = cat_map.get(shift_code)

        # --- XỬ LÝ CA T (NHÌN VỀ TƯƠNG LAI) ---
        next_day_summary = None
        if shift_code == "T":
            # Thử tìm trong list hoặc query DB như logic trước đó
            if i + 1 < len(summary_list):
                potential_next = summary_list[i+1]
                if (potential_next.employee_id == summary.employee_id and 
                    potential_next.target_date == summary.target_date + timedelta(days=1)):
                    next_day_summary = potential_next

            if next_day_summary is None:
                next_date = summary.target_date + timedelta(days=1)
                extra_scans = db.query(models.Attendance).filter(
                    models.Attendance.username == summary.username,
                    func.date(models.Attendance.check_in_time) == next_date
                ).order_by(models.Attendance.check_in_time.asc()).all()
                if extra_scans:
                    next_day_summary = schemas.AttendanceSummary(
                        employee_id=summary.employee_id, username=summary.username,
                        target_date=next_date, scans=extra_scans
                    )

        # Tính toán chi tiết
        c_in, c_out, stat, late, early, img_in, img_out, actual_h, actual_w = calculate_shift_details(
            shift_cat, summary, next_day_summary
        )
        new_record = models.MonthlyRecord(
            employee_id=summary.employee_id,
            date=summary.target_date,
            shift_code=shift_code,
            checkin_time=c_in,
            checkout_time=c_out,
            checkin_image_path=img_in,
            checkout_image_path=img_out,
            status=stat,
            late_minutes=late,
            early_minutes=early,
            actual_hours=actual_h,
            actual_workday=actual_w,
            explanation_status=0
        )
        result_records.append(new_record)

    return result_records


def get_hybrid_monthly_records(db: Session, start_date: date, end_date: date, employee_id: Optional[int] = None):
    # 1. Xác định mốc đầu tháng hiện tại
    today = date.today()
    first_day_of_this_month = date(today.year, today.month, 1)
    
    result_records = []

    # Hàm hỗ trợ tạo filter động
    def apply_filters(query_obj, is_monthly_table=True):
        if employee_id:
            if is_monthly_table:
                return query_obj.filter(models.MonthlyRecord.employee_id == employee_id)
            else:
                # Nếu là bảng Attendance, ta cần tìm username từ employee_id
                emp = db.query(models.Employee).filter(models.Employee.id == employee_id).first()
                return query_obj.filter(models.Attendance.username == emp.username) if emp else query_obj.filter(False)
        return query_obj

    # Kịch bản A: Toàn bộ quá khứ
    if end_date < first_day_of_this_month:
        query = db.query(models.MonthlyRecord).filter(
            models.MonthlyRecord.date >= start_date,
            models.MonthlyRecord.date <= end_date
        )
        return apply_filters(query).all()

    # Kịch bản B: Toàn bộ tháng này (Real-time)
    elif start_date >= first_day_of_this_month:
        return fetch_and_calculate_realtime(db, start_date, end_date, employee_id)

    # Kịch bản C: Giao thoa (Cũ + Mới)
    else:
        # Khoảng 1: MonthlyRecord (Quá khứ)
        last_day_of_prev_month = first_day_of_this_month - timedelta(days=1)
        past_query = db.query(models.MonthlyRecord).filter(
            models.MonthlyRecord.date >= start_date,
            models.MonthlyRecord.date <= last_day_of_prev_month
        )
        result_records.extend(apply_filters(past_query).all())

        # Khoảng 2: Attendance (Tháng này)
        current_records = fetch_and_calculate_realtime(db, first_day_of_this_month, end_date, employee_id)
        result_records.extend(current_records)
        
        result_records.sort(key=lambda x: (x.date, x.employee_id))
        return result_records

def fetch_and_calculate_realtime(db: Session, s_date: date, e_date: date, employee_id: Optional[int] = None):
    # Sử dụng datetime.combine một cách an toàn
    start_dt = datetime.combine(s_date, time.min)
    end_dt = datetime.combine(e_date, time.max)
    
    query = db.query(models.Attendance).filter(
        models.Attendance.check_in_time >= start_dt,
        models.Attendance.check_in_time <= end_dt
    )
    
    if employee_id:
        emp = db.query(models.Employee).filter(models.Employee.id == employee_id).first()
        if not emp:
            return []
        # Chắc chắn rằng emp.username không None
        query = query.filter(models.Attendance.username == emp.username)
    
    raw_data = query.all()
    
    if not raw_data:
        return []
    
    # Đảm bảo hàm này trả về đúng format mà Schema mong đợi
    return process_attendance_to_monthly(db, raw_data)

def group_records_by_employee(
    records: list,
    emp_map: dict[int, models.Employee]
) -> list[schemas.AttendanceSummaryByEmployee]:
    """
    Nhận list MonthlyRecord (đã được lấy từ hybrid service),
    group theo employee_id và tính tổng các chỉ số.
    
    Tách riêng để có thể tái sử dụng (API summary, export Excel, v.v.)
    """
    grouped: dict[int, list] = defaultdict(list)
    for rec in records:
        grouped[rec.employee_id].append(rec)

    summaries = []
    for emp_id, day_records in grouped.items():
        emp = emp_map.get(emp_id)
        if not emp:
            continue

        counters = {s.value: 0 for s in constants.AttendanceStatus}
        total_late_min  = 0
        total_early_min = 0

        for rec in day_records:
            status_val = rec.status if rec.status is not None else constants.AttendanceStatus.ABSENT
            counters[status_val] = counters.get(status_val, 0) + 1
            total_late_min  += (rec.late_minutes  or 0)
            total_early_min += (rec.early_minutes or 0)

        summaries.append(schemas.AttendanceSummaryByEmployee(
            employee_id          = emp.id,
            username             = emp.username,
            full_name            = emp.full_name,
            department           = getattr(emp.department, "name", None) if hasattr(emp, "department") else None,
            position             = getattr(emp, "position", None),
            total_days           = len(day_records),
            present_count            = counters.get(constants.AttendanceStatus.PRESENT,              0),
            late_count               = counters.get(constants.AttendanceStatus.LATE,                 0),
            early_leave_count        = counters.get(constants.AttendanceStatus.EARLY_LEAVE,          0),
            on_leave_count           = counters.get(constants.AttendanceStatus.ON_LEAVE,             0),
            unpaid_leave_count       = counters.get(constants.AttendanceStatus.UNPAID_LEAVE,         0),
            late_and_early_count     = counters.get(constants.AttendanceStatus.LATE_AND_EARLY_LEAVE, 0),
            absent_count             = counters.get(constants.AttendanceStatus.ABSENT,               0),
            total_late_minutes  = total_late_min,
            total_early_minutes = total_early_min,
        ))

    summaries.sort(key=lambda x: x.full_name)
    return summaries


def get_attendance_summary(
    db: Session,
    start_date: date,
    end_date: date,
    employee_id: Optional[int] = None,
    allowed_emp_ids: Optional[set[int]] = None,
) -> list[schemas.AttendanceSummaryByEmployee]:
    """
    Hàm tổng hợp dùng cho API /summary.
    - employee_id: lọc 1 người cụ thể (None = lấy tất cả)
    - allowed_emp_ids: tập emp_id được phép xem (None = không giới hạn / admin)
    """
    raw_records = get_hybrid_monthly_records(db, start_date, end_date, employee_id)

    if not raw_records:
        return []

    # Filter theo phòng ban nếu là Manager lấy bulk
    if employee_id is None and allowed_emp_ids is not None:
        raw_records = [r for r in raw_records if r.employee_id in allowed_emp_ids]

    if not raw_records:
        return []

    # Cache Employee một lần duy nhất
    emp_ids = {r.employee_id for r in raw_records}
    emp_map = {
        e.id: e for e in db.query(models.Employee).filter(
            models.Employee.id.in_(emp_ids)
        ).all()
    }

    return group_records_by_employee(raw_records, emp_map)