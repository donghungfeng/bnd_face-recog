CREATE TABLE `app_configs` (
	`config_key` VARCHAR(256) NOT NULL, 
	`config_value` VARCHAR(2048) NOT NULL, 
	`description` VARCHAR(2048), 
	`updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP, 
	PRIMARY KEY (`config_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `organization_units` (
    `id` INT NOT NULL AUTO_INCREMENT, 
    `unit_code` VARCHAR(50), 
    `unit_name` VARCHAR(255), 
    `unit_type` VARCHAR(50), 
    `parent_id` INT, 
    `order_num` INT, 
    `level` INT, 
    `location` VARCHAR(255), 
    `status` VARCHAR(50), 
    `notes` TEXT, 
    PRIMARY KEY (`id`), 
    UNIQUE KEY `ix_organization_units_unit_code` (`unit_code`),
    CONSTRAINT `fk_org_parent` FOREIGN KEY (`parent_id`) REFERENCES `organization_units` (`id`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `employees` (
	`id` INT NOT NULL AUTO_INCREMENT, 
	`username` VARCHAR(50), 
	`full_name` VARCHAR(512), 
	`phone` VARCHAR(20), 
	`dob` DATE, 
	`email` VARCHAR(512), 
	`department_id` INT, 
	`status` VARCHAR(50),
	`notes` TEXT, 
	`hourly_rate` INT, 
	`allowance` INT, 
	`password` VARCHAR(512), 
	`role` VARCHAR(256), 
	`is_locked` INT, 
	`date_of_birth` DATE, 
	`ccCaNhan` INT DEFAULT 1, 
	`ccTapTrung` INT DEFAULT 0, 
	`checkViTri` INT DEFAULT 1,
	`checkMang` INT DEFAULT 1, 
	PRIMARY KEY (`id`), 
	UNIQUE KEY `ix_employees_username` (`username`),
	KEY `ix_employees_full_name` (`full_name`),
	CONSTRAINT `FK_employees_department` FOREIGN KEY (`department_id`) REFERENCES `organization_units` (`id`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `attendance` (
	`id` INT NOT NULL AUTO_INCREMENT,
	`username` VARCHAR(512),
	`full_name` VARCHAR(512),
	`check_in_time` DATETIME,
	`image_path` VARCHAR(2048),
	`late_minutes` INT,
	`early_minutes` INT,
	`explanation_status` VARCHAR(50),
	`explanation_reason` TEXT,
	`confidence` DOUBLE, 
	`client_ip` TEXT, 
	`latitude` DOUBLE, 
	`longitude` DOUBLE, 
	`attendance_type` VARCHAR(256) DEFAULT 'Tập trung',
	`is_fraud` INT DEFAULT 0, 
	`fraud_note` TEXT, 
	`note` TEXT,
	CONSTRAINT `ATTENDANCE_PK` PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `explanation` (
    `id` INT NOT NULL AUTO_INCREMENT,
    `username` VARCHAR(255) NOT NULL,
    `date` DATE NOT NULL,
    `reason` TEXT NOT NULL,
    `status` VARCHAR(50) NOT NULL,
    `shift_code` VARCHAR(255),
    PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `monthly_records` (
    `id` INT NOT NULL AUTO_INCREMENT,
    `employee_id` INT NOT NULL,
    `shift_code` VARCHAR(50),
    `date` DATE,
    `checkin_time` TIME,
    `checkout_time` TIME,
    `late_minutes` INT DEFAULT 0,
    `early_minutes` INT DEFAULT 0,
    `status` INT DEFAULT 0,
    `explanation_reason` TEXT,
    `explanation_status` INT DEFAULT 0,
    `note` TEXT, 
    `checkin_image_path` TEXT, 
    `checkout_image_path` TEXT, 
    `actual_hours` FLOAT DEFAULT 0, 
    `actual_workday` FLOAT DEFAULT 0,
    PRIMARY KEY (`id`),
    KEY `idx_monthly_records_employee_id` (`employee_id`),
    KEY `idx_monthly_records_date` (`date`),
    CONSTRAINT `fk_monthly_records_employee` FOREIGN KEY (`employee_id`) REFERENCES `employees` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `shift_assignments` (
    `id` INT NOT NULL AUTO_INCREMENT,
    `employee_id` INT NOT NULL,
    `shift_code` VARCHAR(255),
    `shift_date` DATE,
    PRIMARY KEY (`id`),
    KEY `ix_shift_assignments_shift_date` (`shift_date`),
    KEY `ix_shift_assignments_shift_code` (`shift_code`),
    CONSTRAINT `fk_shift_assignments_employee` FOREIGN KEY (`employee_id`) REFERENCES `employees` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `shift_categories` (
    `id` INT NOT NULL AUTO_INCREMENT, 
    `shift_code` VARCHAR(50), 
    `shift_name` VARCHAR(512), 
    `start_time` TIME, 
    `end_time` TIME, 
    `is_overnight` INT, 
    `status` VARCHAR(50), 
    `notes` TEXT, 
    `checkin_from` TIME DEFAULT NULL, 
    `checkin_to` TIME DEFAULT NULL, 
    `checkout_from` TIME DEFAULT NULL, 
    `checkout_to` TIME DEFAULT NULL, 
    `work_hours` DOUBLE DEFAULT NULL, 
    `work_days` DOUBLE DEFAULT NULL, 
    `day_coefficient` DOUBLE DEFAULT NULL, 
    PRIMARY KEY (`id`),
    UNIQUE KEY `ix_shift_categories_shift_code` (`shift_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `wifi` (
    `id` INT NOT NULL AUTO_INCREMENT,
    `name` VARCHAR(512) NOT NULL,
    `password` VARCHAR(512) NOT NULL,
    `location` VARCHAR(512),
    `ip_address` VARCHAR(512),
    `note` TEXT,
    `status` VARCHAR(50) NOT NULL,
    PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE leave_types (
    id INT NOT NULL AUTO_INCREMENT,
    code VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    benefit_rate DECIMAL(5, 2) DEFAULT 100.0,
    max_num_days INT DEFAULT 0,             
    scope TEXT,                             
    status TINYINT DEFAULT 1,
    note TEXT,                              
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE holidays (
    id INT NOT NULL AUTO_INCREMENT,
    code VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    from_date DATE NOT NULL,
    to_date DATE NOT NULL,
    num_days DECIMAL(4, 1) NOT NULL,
    scope TEXT,                             
    status TINYINT DEFAULT 1,
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE leave_requests (
    id INT NOT NULL AUTO_INCREMENT,
    username VARCHAR(255) NOT NULL,
    from_date DATE NOT NULL,
    to_date DATE NOT NULL,
    type_id INT NOT NULL,
    reason TEXT,
    approver_username VARCHAR(255),
    approver_fullname VARCHAR(255),
    status VARCHAR(50) DEFAULT 'PENDING',
    PRIMARY KEY (id),
    CONSTRAINT fk_leave_type FOREIGN KEY (type_id) REFERENCES leave_types(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


