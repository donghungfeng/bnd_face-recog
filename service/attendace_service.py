from datetime import time, date, datetime, timedelta
from collections import defaultdict
from enum import IntEnum
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
import models, schemas, constants

# --- CLASS HELPER ĐỂ GỘP CA ---
class VirtualShiftCategory:
    def __init__(self, shifts):
        self.shift_code = "+".join(s.shift_code for s in shifts)
        self.start_time = shifts[0].start_time
        self.end_time = shifts[-1].end_time
        self.checkin_from = shifts[0].checkin_from
        self.checkin_to = shifts[0].checkin_to
        self.checkout_from = shifts[-1].checkout_from
        self.checkout_to = shifts[-1].checkout_to
        self.work_hours = sum((s.work_hours or 0.0) for s in shifts)
        self.work_days = sum((s.work_days or 0.0) for s in shifts)
        self.is_overnight = any(getattr(s, 'is_overnight', 0) == 1 or s.shift_code == "T" for s in shifts)

# --- CÁC HÀM HỖ TRỢ RIÊNG TƯ (CLEAN CODE) ---

def _merge_adjacent_shifts(assigned_cats):
    """Gộp các ca có giờ kết thúc trùng với giờ bắt đầu của ca sau."""
    if not assigned_cats: return []
    assigned_cats.sort(key=lambda c: c.start_time if c.start_time else time.min)
    merged = []
    current_group = []
    for sc in assigned_cats:
        if not current_group:
            current_group.append(sc)
        else:
            if current_group[-1].end_time == sc.start_time:
                current_group.append(sc)
            else:
                merged.append(VirtualShiftCategory(current_group))
                current_group = [sc]
    if current_group:
        merged.append(VirtualShiftCategory(current_group))
    return merged

def _distribute_scans_to_shifts(merged_shifts, scans, target_date):
    """Phân bổ danh sách chấm công vào từng cụm ca dựa trên ranh giới thời gian."""
    if len(merged_shifts) <= 1:
        return [scans]

    pools = [[] for _ in merged_shifts]
    boundaries = []

    for j in range(len(merged_shifts) - 1):
        m_curr, m_next = merged_shifts[j], merged_shifts[j+1]
        t_limit_start = m_curr.checkout_from or m_curr.end_time
        t_limit_end = m_next.checkin_to or m_next.start_time
        
        dt_start = datetime.combine(target_date, t_limit_start)
        dt_end = datetime.combine(target_date, t_limit_end)
        
        # Tìm các bản ghi nằm trong khoảng giao (tranh chấp)
        overlap = [s for s in scans if dt_start <= s.check_in_time <= dt_end]
        if overlap:
            # Ca trước lấy bản ghi đầu (Giờ ra), ca sau lấy bản ghi cuối (Giờ vào)
            boundaries.append((overlap[0].check_in_time, overlap[-1].check_in_time))
        else:
            boundaries.append((dt_start, dt_end))

    for j in range(len(merged_shifts)):
        for s in scans:
            is_valid = True
            if j > 0 and s.check_in_time < boundaries[j-1][1]: is_valid = False
            if j < len(merged_shifts) - 1 and s.check_in_time > boundaries[j][0]: is_valid = False
            if is_valid: pools[j].append(s)
    return pools

def _get_next_day_scans_for_overnight(db, username, target_date, m_shift):
    """
    Lấy các bản ghi quẹt thẻ vào buổi sáng ngày hôm sau 
    nằm trong khung giờ checkout cho phép của ca đêm.
    """
    next_date = target_date + timedelta(days=1)
    limit_time = getattr(m_shift, 'checkout_to', None) or time(11, 0)
    limit_datetime = datetime.combine(next_date, limit_time)

    extra = db.query(models.Attendance).filter(
        models.Attendance.username == username,
        models.Attendance.check_in_time >= datetime.combine(next_date, time.min),
        models.Attendance.check_in_time <= limit_datetime
    ).order_by(models.Attendance.check_in_time.asc()).all()
    
    return [schemas.AttendanceSchema.from_orm(s) for s in extra]

def _is_overnight_shift(shift_cat) -> bool:
    """Kiểm tra một ca có phải ca thâu đêm không."""
    return shift_cat and (
        shift_cat.shift_code == "T" or 
        getattr(shift_cat, 'is_overnight', 0) == 1
    )

def _get_overnight_checkout_cutoff(m_shift, target_date: date) -> datetime:
    """
    Trả về mốc thời gian tối đa của phần scan "thuộc về ca đêm hôm trước".
    Dùng checkout_to nếu có, fallback là 11:00 sáng ngày hôm sau.
    """
    next_date = target_date + timedelta(days=1)
    limit_time = getattr(m_shift, 'checkout_to', None) or time(11, 0)
    return datetime.combine(next_date, limit_time)


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

def calculate_shift_details(shift_cat, summary, next_day_summary=None):
    c_in, c_out, img_in, img_out = None, None, None, None
    status = constants.AttendanceStatus.ABSENT
    late_min, early_min, actual_hours, actual_workday = 0, 0, 0.0, 0.0

    if not summary or not summary.scans:
        return c_in, c_out, status, late_min, early_min, img_in, img_out, actual_hours, actual_workday

    first_scan = summary.scans[0]
    dt_in = first_scan.check_in_time
    c_in = dt_in.time()
    img_in = getattr(first_scan, 'image_path', None) 

    if shift_cat:
        ref_checkin_to = datetime.combine(summary.target_date, shift_cat.checkin_to)
        if dt_in > ref_checkin_to:
            late_min = int((dt_in - ref_checkin_to).total_seconds() / 60)

    dt_out, now = None, datetime.now()
    is_ovn = shift_cat and (shift_cat.shift_code == "T" or getattr(shift_cat, 'is_overnight', 0) == 1)
    ref_date_out = summary.target_date + timedelta(days=1) if is_ovn else summary.target_date
    end_limit = shift_cat.checkout_from if shift_cat else time(23, 59)
    ref_checkout_limit = datetime.combine(ref_date_out, end_limit)

    if len(summary.scans) > 1:
        last_scan = summary.scans[-1]
        dt_out = last_scan.check_in_time

    if dt_out is None and now >= ref_checkout_limit:
        dt_out = dt_in 
        
    if dt_out:
        c_out = dt_out.time()
        img_out = getattr(last_scan, 'image_path', None) if dt_out != dt_in else img_in

    if dt_out is None and now < ref_checkout_limit:
        status = constants.AttendanceStatus.LATE if late_min > 0 else constants.AttendanceStatus.IN_PROGRESS
        return c_in, None, status, late_min, 0, img_in, None, 0.0, 0.0

    if not shift_cat:
        return c_in, c_out, constants.AttendanceStatus.PRESENT, 0, 0, img_in, img_out, 0.0, 0.0

    ref_checkout_from = datetime.combine(ref_date_out, shift_cat.checkout_from)
    if dt_out:
        if dt_out < ref_checkout_from:
            early_min = int((ref_checkout_from - dt_out).total_seconds() / 60)
        
        if late_min > 0 and early_min > 0: status = constants.AttendanceStatus.LATE_AND_EARLY_LEAVE
        elif late_min > 0: status = constants.AttendanceStatus.LATE
        elif early_min > 0: status = constants.AttendanceStatus.EARLY_LEAVE
        else: status = constants.AttendanceStatus.PRESENT
    else: status = constants.AttendanceStatus.ABSENT

    base_h, base_d = float(getattr(shift_cat, 'work_hours', 0.0)), float(getattr(shift_cat, 'work_days', 0.0))
    if status == constants.AttendanceStatus.PRESENT:
        actual_hours, actual_workday = base_h, base_d
    elif status in [constants.AttendanceStatus.LATE, constants.AttendanceStatus.EARLY_LEAVE]:
        actual_hours, actual_workday = base_h / 2, base_d / 2
    elif status == constants.AttendanceStatus.LATE_AND_EARLY_LEAVE:
        work_duration = (dt_out - dt_in).total_seconds() / 3600 if dt_in and dt_out else 0
        if work_duration >= 4.0:
            actual_hours, actual_workday = base_h / 2, base_d / 2

    return c_in, c_out, status, late_min, early_min, img_in, img_out, actual_hours, actual_workday


def generate_monthly_records(db: Session, summary_list: list[schemas.AttendanceSummary]):
    if not summary_list: return []

    # 1. Caching dữ liệu
    emp_ids = list(set(s.employee_id for s in summary_list))
    dates = list(set(s.target_date for s in summary_list))
    assignments = db.query(models.ShiftAssignment).filter(
        models.ShiftAssignment.employee_id.in_(emp_ids),
        models.ShiftAssignment.shift_date.in_(dates + [d - timedelta(days=1) for d in dates])
    ).all()
    assign_map = {(a.employee_id, a.shift_date): a.shift_code for a in assignments}
    cat_map = {c.shift_code: c for c in db.query(models.ShiftCategory).all()}
    
    result_records = []
    summary_list.sort(key=lambda x: (x.employee_id, x.target_date))

    for i, summary in enumerate(summary_list):
        # ────────────────────────────────────────────────────────────────
        # XỬ LÝ TRƯỜNG HỢP HÔM TRƯỚC LÀM CA ĐÊM
        # ────────────────────────────────────────────────────────────────
        # Lấy ca của hôm qua để kiểm tra có ca đêm không
        prev_shift_str = assign_map.get((summary.employee_id, summary.target_date - timedelta(days=1)), "")
        prev_overnight_cat = None  # ca đêm hôm qua (nếu có)

        for c in [x.strip() for x in prev_shift_str.split(',') if x.strip()]:
            p_cat = cat_map.get(c)
            if p_cat and _is_overnight_shift(p_cat):
                prev_overnight_cat = p_cat
                break

        if prev_overnight_cat is not None:
            # Tính mốc cutoff — scan trước mốc này thuộc về ca đêm hôm qua
            overnight_cutoff = _get_overnight_checkout_cutoff(
                prev_overnight_cat, summary.target_date - timedelta(days=1)
            )

            # Lọc ra các scan KHÔNG thuộc về ca đêm hôm qua (tức là sau mốc cutoff)
            remaining_scans = [
                s for s in summary.scans
                if s.check_in_time > overnight_cutoff
            ]

            # Nếu không còn scan nào sau cutoff → toàn bộ ngày này là "đuôi" ca đêm,
            # bỏ qua hoàn toàn như logic cũ
            if not remaining_scans:
                continue

            # Còn scan → có ca làm việc riêng trong ngày hôm nay
            # Tiếp tục xử lý nhưng CHỈ với các scan sau cutoff
            summary = schemas.AttendanceSummary(
                employee_id=summary.employee_id,
                username=summary.username,
                target_date=summary.target_date,
                scans=remaining_scans
            )
        # ────────────────────────────────────────────────────────────────

        # Tách và gộp ca của ngày hôm nay
        shift_str = assign_map.get((summary.employee_id, summary.target_date), "X")
        codes = [c.strip() for c in shift_str.split(',') if c.strip()]
        assigned_cats = [cat_map[c] for c in codes if c in cat_map]
        merged_shifts = _merge_adjacent_shifts(assigned_cats)

        # Phân bổ Scans vào từng ca
        scan_pools = _distribute_scans_to_shifts(merged_shifts, summary.scans, summary.target_date)

        for j, m_shift in enumerate(merged_shifts):
            current_scans = list(scan_pools[j])
            
            # Logic bổ sung scan buổi sáng hôm sau cho ca thâu đêm
            if _is_overnight_shift(m_shift):
                next_morning_scans = _get_next_day_scans_for_overnight(
                    db, summary.username, summary.target_date, m_shift
                )
                if next_morning_scans:
                    current_scans.extend(next_morning_scans)
            
            virt_summary = schemas.AttendanceSummary(
                employee_id=summary.employee_id, username=summary.username,
                target_date=summary.target_date, scans=current_scans
            )
            
            det = calculate_shift_details(m_shift, virt_summary)
            
            result_records.append(models.MonthlyRecord(
                employee_id=summary.employee_id, date=summary.target_date, shift_code=m_shift.shift_code,
                checkin_time=det[0], checkout_time=det[1], status=det[2],
                late_minutes=det[3], early_minutes=det[4],
                checkin_image_path=det[5], checkout_image_path=det[6],
                actual_hours=det[7], actual_workday=det[8], explanation_status=0
            ))
    return result_records


def get_hybrid_monthly_records(db: Session, start_date: date, end_date: date, employee_id: Optional[int] = None):
    today = date.today()
    first_day_of_this_month = date(today.year, today.month, 1)
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