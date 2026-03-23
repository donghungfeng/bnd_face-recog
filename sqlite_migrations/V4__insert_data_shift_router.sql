-- V4: Import dữ liệu danh mục ca làm việc từ hình ảnh
-- Lưu ý: Các trường không có dữ liệu trong hình sẽ được để là NULL

INSERT INTO shift_categories (
    shift_code, 
    shift_name, 
    start_time, 
    end_time, 
    checkin_from, 
    checkin_to, 
    checkout_from, 
    checkout_to, 
    work_hours, 
    work_days, 
    day_coefficient,
    is_overnight,
    status
) VALUES 
-- Dòng 1: Ngày làm việc đủ
(
    'X', 
    'Ngày làm việc đủ', 
    '07:30', 
    '16:30', 
    NULL,     -- Giờ chấm bắt đầu ca từ (trống)
    '07:40',  -- Giờ chấm bắt đầu ca đến
    '16:20',  -- Giờ chấm kết thúc ca từ
    NULL,     -- Giờ chấm kết thúc ca đến (trống)
    8,        -- Giờ công
    1,        -- Ngày công
    NULL,     -- Hệ số ngày (trống)
    0,        -- Không phải ca qua đêm
    'Active'
),

-- Dòng 2: Làm chế độ 7h/ngày
(
    'X-', 
    'Làm chế độ 7h/ngày', 
    '08:00', 
    '16:00', 
    NULL, 
    '07:50', 
    '15:50', 
    NULL, 
    7, 
    1, 
    NULL, 
    0, 
    'Active'
),

-- Dòng 3: Trực 24h
(
    'T', 
    'Trực 24h', 
    '07:30', 
    '07:30', 
    NULL, 
    '07:40', 
    '07:20', 
    NULL, 
    24, 
    2, 
    NULL, 
    1,        -- Ca 24h thường tính là qua đêm/gối đầu
    'Active'
);