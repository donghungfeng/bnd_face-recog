from enum import IntEnum

class AttendanceStatus(IntEnum):
    """Trạng thái chấm công (Lưu DB là số)"""
    ABSENT = 0           # Vắng mặt
    PRESENT = 1          # Đi làm đúng giờ
    LATE = 2             # Đi muộn
    EARLY_LEAVE = 3      # Về sớm
    ON_LEAVE = 4         # Nghỉ phép có lương
    UNPAID_LEAVE = 5     # Nghỉ không lương
    LATE_AND_EARLY_LEAVE = 6 # Đi muộn & Về sớm
    IN_PROGRESS = 7

class ExplanationStatus(IntEnum):
    """Trạng thái giải trình"""
    NONE = 0             # Không có giải trình
    PENDING = 1          # Chờ duyệt
    APPROVED = 2         # Đã duyệt
    REJECTED = 3         # Từ chối