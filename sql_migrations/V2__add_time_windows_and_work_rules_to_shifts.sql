-- MySQL Migration: Thêm các cột với giá trị mặc định là NULL
ALTER TABLE shift_categories 
ADD COLUMN checkin_from TIME DEFAULT NULL AFTER end_time,
ADD COLUMN checkin_to TIME DEFAULT NULL AFTER checkin_from,
ADD COLUMN checkout_from TIME DEFAULT NULL AFTER checkin_to,
ADD COLUMN checkout_to TIME DEFAULT NULL AFTER checkout_from,
ADD COLUMN work_hours DOUBLE DEFAULT NULL AFTER checkout_to,
ADD COLUMN work_days DOUBLE DEFAULT NULL AFTER work_hours,
ADD COLUMN day_coefficient DOUBLE DEFAULT NULL AFTER work_days;