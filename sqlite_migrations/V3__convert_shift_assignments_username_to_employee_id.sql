-- 1. Xóa bảng cũ nếu tồn tại
DROP TABLE IF EXISTS shift_assignments;

-- 2. Tạo lại bảng với cấu trúc employee_id và Foreign Key
CREATE TABLE shift_assignments (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL,
    shift_code VARCHAR(255),
    shift_date DATE,
    FOREIGN KEY(employee_id) REFERENCES employees(id) ON DELETE CASCADE
);

-- 3. Tạo lại các Index để tăng tốc độ truy vấn
CREATE INDEX ix_shift_assignments_shift_date ON shift_assignments (shift_date);
CREATE INDEX ix_shift_assignments_employee_id ON shift_assignments (employee_id);
CREATE INDEX ix_shift_assignments_shift_code ON shift_assignments (shift_code);