-- SQLite Migration: Thêm các cột mặc định nhận giá trị NULL
ALTER TABLE shift_categories ADD COLUMN checkin_from TIME DEFAULT NULL;
ALTER TABLE shift_categories ADD COLUMN checkin_to TIME DEFAULT NULL;
ALTER TABLE shift_categories ADD COLUMN checkout_from TIME DEFAULT NULL;
ALTER TABLE shift_categories ADD COLUMN checkout_to TIME DEFAULT NULL;
ALTER TABLE shift_categories ADD COLUMN work_hours REAL DEFAULT NULL;
ALTER TABLE shift_categories ADD COLUMN work_days REAL DEFAULT NULL;
ALTER TABLE shift_categories ADD COLUMN day_coefficient REAL DEFAULT NULL;