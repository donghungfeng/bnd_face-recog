-- 1. Tạo bảng mới employee_departments
CREATE TABLE `employee_departments` (
    `id` INT NOT NULL AUTO_INCREMENT,
    `employee_id` INT NOT NULL,
    `department_id` INT NOT NULL,
    `role` VARCHAR(256),
    `is_primary` TINYINT DEFAULT 1,
    `status` VARCHAR(50) DEFAULT 'active',
    `assigned_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `unique_emp_dept` (`employee_id`, `department_id`),
    CONSTRAINT `fk_emp_dept_employee` FOREIGN KEY (`employee_id`) REFERENCES `employees` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_emp_dept_unit` FOREIGN KEY (`department_id`) REFERENCES `organization_units` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. Insert dữ liệu từ bảng employees cũ sang bảng mới
-- Chúng ta lấy department_id và role hiện tại làm phòng ban chính (is_primary = 1)
INSERT INTO `employee_departments` (employee_id, department_id, role, is_primary, status, assigned_at)
SELECT 
    id, 
    department_id, 
    role, 
    1, -- Mặc định những gì đang có là phòng ban chính
    'active', 
    NOW() 
FROM `employees`
WHERE department_id IS NOT NULL;