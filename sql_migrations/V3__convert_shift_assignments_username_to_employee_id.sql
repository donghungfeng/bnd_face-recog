-- 1. Xóa cột username cũ và index liên quan
DROP INDEX ix_shift_assignments_username ON shift_assignments;
ALTER TABLE shift_assignments DROP COLUMN username;

-- 2. Thêm cột employee_id mới (INT) và đặt sau cột id
ALTER TABLE shift_assignments ADD COLUMN employee_id INT NOT NULL AFTER id;

-- 3. Tạo Index và Khóa ngoại (Foreign Key)
CREATE INDEX ix_shift_assignments_employee_id ON shift_assignments (employee_id);
ALTER TABLE shift_assignments 
ADD CONSTRAINT fk_shift_assignments_employee 
FOREIGN KEY (employee_id) REFERENCES employees(id) 
ON DELETE CASCADE;