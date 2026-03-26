-- Thêm cấu hình chấm công cá nhân/tập trung và check vị trí/mạng cho nhân viên
ALTER TABLE employees ADD COLUMN ccCaNhan INTEGER DEFAULT 1;
ALTER TABLE employees ADD COLUMN ccTapTrung INTEGER DEFAULT 0;
ALTER TABLE employees ADD COLUMN checkViTri INTEGER DEFAULT 1;
ALTER TABLE employees ADD COLUMN checkMang INTEGER DEFAULT 1;