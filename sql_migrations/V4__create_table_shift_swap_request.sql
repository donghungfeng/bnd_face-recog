-- V4__create_table_shift_swap_request.sql

CREATE TABLE shift_swap_request (
    id INT AUTO_INCREMENT PRIMARY KEY,
    employee_source_id INT NOT NULL,
    employee_target_id INT, 
    source_date DATE NOT NULL,
    target_date DATE NOT NULL,
    -- Cho phép NULL để hỗ trợ đổi cả ngày
    source_shift_code VARCHAR(50) NULL,
    target_shift_code VARCHAR(50) NULL,
    -- Trường đánh dấu đổi cả ngày (0: Không, 1: Có)
    is_all_day INT DEFAULT 0,
    
    reason TEXT,
    status VARCHAR(20) DEFAULT 'PENDING', 
    approved_by_id INT,
    attached_file VARCHAR(1024) NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    CONSTRAINT fk_swap_source_emp FOREIGN KEY (employee_source_id) REFERENCES employees(id),
    CONSTRAINT fk_swap_target_emp FOREIGN KEY (employee_target_id) REFERENCES employees(id),
    CONSTRAINT fk_swap_approved_by FOREIGN KEY (approved_by_id) REFERENCES employees(id)
);