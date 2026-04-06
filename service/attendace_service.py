from datetime import time, date, datetime, timedelta
from collections import defaultdict
from enum import IntEnum
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
import models, schemas, constants

# --- CÁC HÀM HỖ TRỢ RIÊNG TƯ ---

def _is_overnight_shift(shift_cat) -> bool:
    """Kiểm tra một ca có phải ca thâu đêm không."""
    return shift_cat and (
        shift_cat.shift_code == "T" or 
        getattr(shift_cat, 'is_overnight', 0) == 1
    )

def calculate_shift_details(shift_dict, c_in_dt, c_out_dt, img_in, img_out):
    """
    Tính toán giờ In/Out, trạng thái, đi muộn, về sớm và số công cho TỪNG CA riêng biệt.
    Dùng chung logic tính công cũ nhưng dựa trên datetime object thay vì scan objects.
    """
    cat = shift_dict['cat']
    # 🌟 Đọc cờ nhận diện xem ca này là hệ thống tự xếp hay quản lý xếp
    is_auto_schedule = shift_dict.get('is_auto_schedule', False) 
    
    status = constants.AttendanceStatus.ABSENT
    late_min, early_min, actual_hours, actual_workday = 0, 0, 0.0, 0.0
    
    c_in = c_in_dt.time() if c_in_dt else None
    c_out = None
    
    # --- 🌟 LOGIC MỚI: CHỈ ĐỔI STATUS NẾU LÀ CA X "TỰ ĐỘNG" ---
    def resolve_final_status(computed_status):
        if is_auto_schedule: # Nếu hệ thống tự nhét ca X vào -> Chưa có lịch
            return constants.AttendanceStatus.NO_SCHEDULE
        elif cat.shift_code in ["X-", "X-/2"]: # Vẫn giữ logic Chế độ 7h
            return constants.AttendanceStatus.SEVEN_HOURS
        return computed_status # Ca X do quản lý xếp thì vẫn trả về PRESENT/LATE/EARLY... như bình thường
    # -----------------------------------------------------------------------------------

    # Tính đi muộn
    if c_in_dt and c_in_dt > shift_dict['checkin_to']:
        late_min = int((c_in_dt - shift_dict['checkin_to']).total_seconds() / 60)
        
    now = datetime.now()
    ref_checkout_limit = shift_dict['checkout_from'] 
    
    # Auto-close: Nếu đã quá giờ kết thúc ca mà chưa có checkout
    if c_out_dt is None and now >= ref_checkout_limit:
        c_out_dt = c_in_dt
        
    if c_out_dt:
        c_out = c_out_dt.time()
        if img_out is None and c_out_dt == c_in_dt:
            img_out = img_in
            
    # Vắng mặt (Không In, Không Out)
    if not c_in_dt and not c_out_dt:
        return None, None, resolve_final_status(constants.AttendanceStatus.ABSENT), 0, 0, None, None, 0.0, 0.0
    # Ca đang diễn ra
    if c_out_dt is None and now < ref_checkout_limit:
        status = constants.AttendanceStatus.LATE if late_min > 0 else constants.AttendanceStatus.IN_PROGRESS
        return c_in, None, resolve_final_status(status), late_min, 0, img_in, None, 0.0, 0.0

    # Tính về sớm và chốt Status
    if c_out_dt:
        if c_out_dt < ref_checkout_limit:
            early_min = int((ref_checkout_limit - c_out_dt).total_seconds() / 60)
            
        if late_min > 0 and early_min > 0: status = constants.AttendanceStatus.LATE_AND_EARLY_LEAVE
        elif late_min > 0: status = constants.AttendanceStatus.LATE
        elif early_min > 0: status = constants.AttendanceStatus.EARLY_LEAVE
        else: status = constants.AttendanceStatus.PRESENT
    else:
        status = constants.AttendanceStatus.ABSENT

    # Tính công dựa theo Status gốc
    base_h = float(getattr(cat, 'work_hours', None) or 0.0)
    base_d = float(getattr(cat, 'work_days', None) or 0.0)
    if status == constants.AttendanceStatus.PRESENT:
        actual_hours, actual_workday = base_h, base_d
    elif status in [constants.AttendanceStatus.LATE, constants.AttendanceStatus.EARLY_LEAVE]:
        actual_hours, actual_workday = base_h / 2, base_d / 2
    elif status == constants.AttendanceStatus.LATE_AND_EARLY_LEAVE:
        work_duration = (c_out_dt - c_in_dt).total_seconds() / 3600 if c_in_dt and c_out_dt else 0
        if work_duration >= 4.0:  # Trâm chước nửa công nếu có mặt quá 4 tiếng
            actual_hours, actual_workday = base_h / 2, base_d / 2

    # ÁP DỤNG TRẠNG THÁI MỚI VÀO OUTPUT
    return c_in, c_out, resolve_final_status(status), late_min, early_min, img_in, img_out, actual_hours, actual_workday


# --- CÁC HÀM XỬ LÝ CHÍNH ---

def process_attendance_to_monthly(db, list_data):
    monthlyRecords = group_attendance_to_summaries(db, list_data)
    result = generate_monthly_records(db, monthlyRecords)
    return result

def group_attendance_to_summaries(db: Session, attendance_list: list[models.Attendance]) -> list[schemas.AttendanceSummary]:
    unique_usernames = list(set(a.username for a in attendance_list))
    employee_map = {
        e.username: e.id 
        for e in db.query(models.Employee.id, models.Employee.username)
                 .filter(models.Employee.username.in_(unique_usernames)).all()
    }
    grouped_data = defaultdict(list)
    for att in attendance_list:
        emp_id = employee_map.get(att.username)
        if not emp_id: continue 
        att_date = att.check_in_time.date()
        key = (emp_id, att.username, att_date)
        grouped_data[key].append(att)

    summaries = []
    for (emp_id, uname, target_date), scans in grouped_data.items():
        scans.sort(key=lambda x: x.check_in_time)
        summaries.append(schemas.AttendanceSummary(
            employee_id=emp_id,
            username=uname,
            target_date=target_date,
            scans=[schemas.AttendanceSchema.from_orm(s) for s in scans]
        ))
    return summaries

def generate_monthly_records(db: Session, summary_list: list[schemas.AttendanceSummary]):
    if not summary_list: return []

    emp_ids = list(set(s.employee_id for s in summary_list))
    dates = list(set(s.target_date for s in summary_list))
    
    # Mở rộng biên độ tìm kiếm ra hôm qua và ngày mai để hứng các Ca Đêm nối ngày
    min_date = min(dates) - timedelta(days=1)
    max_date = max(dates) + timedelta(days=1)
    
    assignments = db.query(models.ShiftAssignment).filter(
        models.ShiftAssignment.employee_id.in_(emp_ids),
        models.ShiftAssignment.shift_date >= min_date,
        models.ShiftAssignment.shift_date <= max_date
    ).all()
    
    assign_map = defaultdict(list)
    for a in assignments:
        assign_map[a.employee_id].append(a)
        
    cat_map = {c.shift_code: c for c in db.query(models.ShiftCategory).all()}
    
    result_records = []
    
    emp_summaries = defaultdict(list)
    for s in summary_list:
        emp_summaries[s.employee_id].append(s)
        
    for emp_id in emp_ids:
        # 1. TỔNG HỢP LỊCH LÀM VIỆC VÀ NGÀY QUẸT THẺ
        emp_schedule_map = defaultdict(list)
        for a in assign_map[emp_id]:
            emp_schedule_map[a.shift_date].extend([c.strip() for c in a.shift_code.split(',') if c.strip()])

        # --- 🌟 THEO DÕI NHỮNG NGÀY BỊ THIẾU LỊCH VÀ PHẢI TỰ CHÈN CA X ---
        auto_assigned_dates = set()

        for s in emp_summaries[emp_id]:
            if s.target_date not in emp_schedule_map or not emp_schedule_map[s.target_date]:
                emp_schedule_map[s.target_date] = ["X"]
                auto_assigned_dates.add(s.target_date)

        # --- 🌟 XÁC ĐỊNH NGÀY CẦN BỎ QUA ---
        # Nếu ngày D không có lịch (auto X) VÀ ngày D-1 có ca qua đêm thật sự
        # thì ngày D không cần tạo bản ghi riêng — scan cuối thuộc về ca đêm D-1
        skip_dates = set()
        for d in auto_assigned_dates:
            prev_day = d - timedelta(days=1)
            prev_codes = emp_schedule_map.get(prev_day, [])
            # Chỉ xét ngày hôm trước nếu đó là lịch thật (không phải cũng auto-assigned)
            prev_is_real = prev_day not in auto_assigned_dates
            if prev_is_real and any(
                _is_overnight_shift(cat_map.get(c))
                for c in prev_codes
                if c in cat_map
            ):
                skip_dates.add(d)

        # 🌟 Ngày hợp lệ để tạo bản ghi cho employee này:
        # loại bỏ skip_dates vì scan của những ngày đó thuộc ca đêm hôm trước
        # → dù startDate truy vấn = ngày D, cũng không hiển thị bản ghi ngày D
        emp_dates = {s.target_date for s in emp_summaries[emp_id]}
        emp_valid_dates = emp_dates - skip_dates

        # Nếu ngày D là skip_date thì ca đêm D-1 cần được tạo bản ghi
        for d in skip_dates:
            emp_valid_dates.add(d - timedelta(days=1))

        # 2. TRẢI PHẲNG (FLATTEN) THÀNH CHUỖI THỜI GIAN
        shifts_chain = []
        all_dates = sorted(list(emp_schedule_map.keys()))
        
        for d in all_dates:
            codes = emp_schedule_map[d]
            for c in codes:
                if c in cat_map:
                    cat = cat_map[c]
                    is_ovn = _is_overnight_shift(cat)
                    
                    s_time = getattr(cat, 'start_time', time.min)
                    e_time = getattr(cat, 'end_time', time.max)
                    ci_to = getattr(cat, 'checkin_to', None)
                    co_from = getattr(cat, 'checkout_from', None)
                    
                    start_dt = datetime.combine(d, s_time)
                    end_dt = datetime.combine(d + timedelta(days=1 if is_ovn else 0), e_time)
                    
                    checkin_to_dt = datetime.combine(d, ci_to) if ci_to else start_dt
                    checkout_from_dt = datetime.combine(d + timedelta(days=1 if is_ovn else 0), co_from) if co_from else end_dt
                    
                    # Xác định xem ca X này có phải là do hệ thống tự chèn không
                    is_auto = (d in auto_assigned_dates) and (c == "X")

                    shifts_chain.append({
                        'date': d, 'shift_code': cat.shift_code, 'cat': cat,
                        'start_dt': start_dt, 'end_dt': end_dt,
                        'checkin_to': checkin_to_dt, 'checkout_from': checkout_from_dt,
                        'is_auto_schedule': is_auto
                    })
                    
        shifts_chain.sort(key=lambda x: x['start_dt'])
        
        # 3. TRẢI PHẲNG TOÀN BỘ SCANS
        emp_scans = []
        for s in emp_summaries[emp_id]:
            emp_scans.extend(s.scans)
        emp_scans.sort(key=lambda x: x.check_in_time) 
        
        if not shifts_chain: continue
            
        N = len(shifts_chain)
        shift_in_dt = [None] * N
        shift_out_dt = [None] * N
        shift_in_img = [None] * N
        shift_out_img = [None] * N
        now = datetime.now()
        
        # ====================================================================================
        # RULE 1 & 2: Ranh giới giao ca (Contiguous & Gap)
        # ====================================================================================
        for i in range(N - 1):
            s_curr = shifts_chain[i]
            s_next = shifts_chain[i+1]
            
            is_same_day = s_curr['date'] == s_next['date']
            is_curr_overnight = _is_overnight_shift(s_curr['cat'])
            
            if not (is_same_day or is_curr_overnight):
                continue
                
            if is_curr_overnight and s_next['is_auto_schedule']:
                continue
            e_curr = s_curr['end_dt']
            s_next_start = s_next['start_dt']
            
            if e_curr == s_next_start:
                if e_curr <= now:
                    shift_out_dt[i] = e_curr
                    shift_in_dt[i+1] = e_curr
                    exact = [s for s in emp_scans if s.check_in_time == e_curr]
                    if exact:
                        shift_out_img[i] = getattr(exact[0], 'image_path', None)
                        shift_in_img[i+1] = getattr(exact[-1], 'image_path', None)
                    
            elif e_curr < s_next_start:
                gap_scans = [s for s in emp_scans if e_curr <= s.check_in_time <= s_next_start]
                if len(gap_scans) >= 2:
                    shift_out_dt[i] = gap_scans[0].check_in_time
                    shift_out_img[i] = getattr(gap_scans[0], 'image_path', None)
                    shift_in_dt[i+1] = gap_scans[-1].check_in_time
                    shift_in_img[i+1] = getattr(gap_scans[-1], 'image_path', None)
                elif len(gap_scans) == 1:
                    shift_out_dt[i] = gap_scans[0].check_in_time
                    shift_out_img[i] = getattr(gap_scans[0], 'image_path', None)
        
        # ====================================================================================
        # BƯỚC ĐIỀN KHUYẾT: Tuân thủ chặt chẽ ranh giới ngày
        # ====================================================================================
        for i in range(N):
            s_curr = shifts_chain[i]
            
            # Quét tìm Check-in
            if shift_in_dt[i] is None:
                search_start = datetime.min
                if i > 0:
                    prev_shift = shifts_chain[i-1]
                    is_same_day = s_curr['date'] == prev_shift['date']
                    is_prev_overnight = _is_overnight_shift(prev_shift['cat'])
                    
                    if is_same_day or is_prev_overnight:
                        search_start = prev_shift['end_dt']
                        if shift_out_dt[i-1] is not None and prev_shift['end_dt'] < s_curr['start_dt']:
                            search_start = max(search_start, shift_out_dt[i-1])
                    else:
                        search_start = datetime.combine(s_curr['date'], time.min)
                else:
                    search_start = datetime.combine(s_curr['date'], time.min)
                    
                avail = [s for s in emp_scans if s.check_in_time > search_start and s.check_in_time <= s_curr['end_dt']]
                if avail:
                    shift_in_dt[i] = avail[0].check_in_time
                    shift_in_img[i] = getattr(avail[0], 'image_path', None)

            # Quét tìm Check-out
            if shift_out_dt[i] is None:
                search_start = s_curr['start_dt']
                if shift_in_dt[i] is not None:
                    search_start = max(search_start, shift_in_dt[i])

                is_curr_overnight = _is_overnight_shift(s_curr['cat'])
                next_day = s_curr['date'] + timedelta(days=1)

                # 🌟 Ca qua đêm + ngày hôm sau không có lịch thật →
                # checkout là bản ghi cuối cùng của ngày hôm sau, không bị chặn bởi ca X
                if is_curr_overnight and next_day in auto_assigned_dates:
                    search_end = datetime.combine(next_day, time.max)
                elif i < N - 1:
                    next_shift = shifts_chain[i+1]
                    is_same_day = s_curr['date'] == next_shift['date']

                    if is_same_day or is_curr_overnight:
                        search_end = next_shift['start_dt']
                    else:
                        end_date = s_curr['date'] + timedelta(days=1 if is_curr_overnight else 0)
                        search_end = datetime.combine(end_date, time.max)
                else:
                    end_date = s_curr['date'] + timedelta(days=1 if is_curr_overnight else 0)
                    search_end = datetime.combine(end_date, time.max)
                
                avail = [s for s in emp_scans if s.check_in_time >= search_start and s.check_in_time <= search_end]
                if avail:
                    shift_out_dt[i] = avail[-1].check_in_time
                    shift_out_img[i] = getattr(avail[-1], 'image_path', None)
            
            if shift_in_dt[i] == shift_out_dt[i] and shift_in_dt[i] is not None:
                if s_curr['end_dt'] != shift_out_dt[i]: 
                    shift_out_dt[i] = None
                    shift_out_img[i] = None

        # ====================================================================================
        # KHỞI TẠO BẢN GHI
        # ====================================================================================
        for i in range(N):
            s_curr = shifts_chain[i]
            # emp_valid_dates đã loại sẵn skip_dates — một điều kiện duy nhất
            if s_curr['date'] not in emp_valid_dates: continue
                
            c_in, c_out, status, late, early, img_in, img_out, hrs, days = calculate_shift_details(
                s_curr, shift_in_dt[i], shift_out_dt[i], shift_in_img[i], shift_out_img[i]
            )
            
            result_records.append(models.MonthlyRecord(
                employee_id=emp_id, date=s_curr['date'], shift_code=s_curr['shift_code'],
                checkin_time=c_in, checkout_time=c_out, status=status,
                late_minutes=late, early_minutes=early,
                checkin_image_path=img_in, checkout_image_path=img_out,
                actual_hours=hrs, actual_workday=days, explanation_status=0
            ))
            
    return result_records

def get_hybrid_monthly_records(db: Session, start_date: date, end_date: date, employee_id: Optional[int] = None):
    today = date.today()
    if today.month == 1:
        first_day_of_this_month = date(today.year - 1, 12, 1)
    else:
        first_day_of_this_month = date(today.year, today.month - 1, 1)
    result_records = []

    def apply_filters(query_obj, is_monthly_table=True):
        if employee_id:
            if is_monthly_table: return query_obj.filter(models.MonthlyRecord.employee_id == employee_id)
            emp = db.query(models.Employee).filter(models.Employee.id == employee_id).first()
            return query_obj.filter(models.Attendance.username == emp.username) if emp else query_obj.filter(False)
        return query_obj

    if end_date < first_day_of_this_month:
        query = db.query(models.MonthlyRecord).filter(models.MonthlyRecord.date >= start_date, models.MonthlyRecord.date <= end_date)
        return apply_filters(query).all()
    elif start_date >= first_day_of_this_month:
        return fetch_and_calculate_realtime(db, start_date, end_date, employee_id)
    else:
        last_day_prev = first_day_of_this_month - timedelta(days=1)
        past_query = db.query(models.MonthlyRecord).filter(models.MonthlyRecord.date >= start_date, models.MonthlyRecord.date <= last_day_prev)
        result_records.extend(apply_filters(past_query).all())
        result_records.extend(fetch_and_calculate_realtime(db, first_day_of_this_month, end_date, employee_id))
        result_records.sort(key=lambda x: (x.date, x.employee_id))
        return result_records

def fetch_and_calculate_realtime(db: Session, s_date: date, e_date: date, employee_id: Optional[int] = None):
    start_dt = datetime.combine(s_date, time.min)
    end_dt = datetime.combine(e_date, time.max)
    query = db.query(models.Attendance).filter(models.Attendance.check_in_time >= start_dt, models.Attendance.check_in_time <= end_dt)
    if employee_id:
        emp = db.query(models.Employee).filter(models.Employee.id == employee_id).first()
        if not emp: return []
        query = query.filter(models.Attendance.username == emp.username)
    raw_data = query.all()
    return process_attendance_to_monthly(db, raw_data) if raw_data else []

def group_records_by_employee(records: list, emp_map: dict[int, models.Employee]) -> list[schemas.AttendanceSummaryByEmployee]:
    grouped = defaultdict(list)
    for rec in records: grouped[rec.employee_id].append(rec)
    summaries = []
    for emp_id, day_records in grouped.items():
        emp = emp_map.get(emp_id)
        if not emp: continue
        counters = {s.value: 0 for s in constants.AttendanceStatus}
        t_late, t_early = 0, 0
        for rec in day_records:
            status_val = rec.status if rec.status is not None else constants.AttendanceStatus.ABSENT
            counters[status_val] = counters.get(status_val, 0) + 1
            t_late += (rec.late_minutes or 0)
            t_early += (rec.early_minutes or 0)
        summaries.append(schemas.AttendanceSummaryByEmployee(
            employee_id=emp.id, username=emp.username, full_name=emp.full_name,
            department=getattr(emp.department, "name", None) if hasattr(emp, "department") else None,
            position=getattr(emp, "position", None), total_days=len(day_records),
            present_count=counters.get(constants.AttendanceStatus.PRESENT, 0),
            late_count=counters.get(constants.AttendanceStatus.LATE, 0),
            early_leave_count=counters.get(constants.AttendanceStatus.EARLY_LEAVE, 0),
            on_leave_count=counters.get(constants.AttendanceStatus.ON_LEAVE, 0),
            unpaid_leave_count=counters.get(constants.AttendanceStatus.UNPAID_LEAVE, 0),
            late_and_early_count=counters.get(constants.AttendanceStatus.LATE_AND_EARLY_LEAVE, 0),
            absent_count=counters.get(constants.AttendanceStatus.ABSENT, 0),
            total_late_minutes=t_late, total_early_minutes=t_early,
        ))
    summaries.sort(key=lambda x: x.full_name)
    return summaries

def get_attendance_summary(db: Session, start_date: date, end_date: date, employee_id: Optional[int] = None, allowed_emp_ids: Optional[set[int]] = None):
    raw_records = get_hybrid_monthly_records(db, start_date, end_date, employee_id)
    if not raw_records: return []
    if employee_id is None and allowed_emp_ids is not None:
        raw_records = [r for r in raw_records if r.employee_id in allowed_emp_ids]
    if not raw_records: return []
    emp_ids = {r.employee_id for r in raw_records}
    emp_map = {e.id: e for e in db.query(models.Employee).filter(models.Employee.id.in_(emp_ids)).all()}
    return group_records_by_employee(raw_records, emp_map)