-- bnd_temp.app_configs definition

CREATE TABLE `app_configs` (
  `config_key` varchar(50) COLLATE utf8mb4_general_ci NOT NULL,
  `config_value` varchar(255) COLLATE utf8mb4_general_ci NOT NULL,
  `description` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  PRIMARY KEY (`config_key`),
  KEY `ix_app_configs_config_key` (`config_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;


-- bnd_temp.attendance definition

CREATE TABLE `attendance` (
  `id` int NOT NULL AUTO_INCREMENT,
  `username` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `full_name` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `check_in_time` datetime DEFAULT NULL,
  `image_path` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `late_minutes` int DEFAULT NULL,
  `early_minutes` int DEFAULT NULL,
  `explanation_status` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `explanation_reason` text COLLATE utf8mb4_general_ci,
  `confidence` double DEFAULT NULL,
  `is_fraud` int DEFAULT '0',
  `fraud_note` text COLLATE utf8mb4_general_ci,
  `client_ip` text COLLATE utf8mb4_general_ci,
  `latitude` double DEFAULT NULL,
  `longitude` double DEFAULT NULL,
  `attendance_type` text COLLATE utf8mb4_general_ci DEFAULT (_utf8mb4'Tập trung'),
  `note` text COLLATE utf8mb4_general_ci,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=110 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;


-- bnd_temp.leave_requests definition

CREATE TABLE `leave_requests` (
  `id` int NOT NULL AUTO_INCREMENT,
  `username` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `full_name` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `leave_date` date DEFAULT NULL,
  `reason` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `approver` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `status` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_leave_requests_id` (`id`),
  KEY `ix_leave_requests_leave_date` (`leave_date`),
  KEY `ix_leave_requests_username` (`username`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;


-- bnd_temp.shift_assignments definition

CREATE TABLE `shift_assignments` (
  `id` int NOT NULL AUTO_INCREMENT,
  `username` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `shift_code` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `shift_date` date DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_shift_assignments_shift_code` (`shift_code`),
  KEY `ix_shift_assignments_username` (`username`),
  KEY `ix_shift_assignments_shift_date` (`shift_date`),
  KEY `ix_shift_assignments_id` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;


-- bnd_temp.shift_categories definition

CREATE TABLE `shift_categories` (
  `id` int NOT NULL AUTO_INCREMENT,
  `shift_code` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `shift_name` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `start_time` time DEFAULT NULL,
  `end_time` time DEFAULT NULL,
  `is_overnight` int DEFAULT NULL,
  `status` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `notes` text COLLATE utf8mb4_general_ci,
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_shift_categories_shift_code` (`shift_code`),
  KEY `ix_shift_categories_id` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;


-- bnd_temp.organization_units definition

CREATE TABLE `organization_units` (
  `id` int NOT NULL AUTO_INCREMENT,
  `unit_code` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `unit_name` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `unit_type` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `parent_id` int DEFAULT NULL,
  `order_num` int DEFAULT NULL,
  `level` int DEFAULT NULL,
  `location` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `status` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `notes` text COLLATE utf8mb4_general_ci,
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_organization_units_unit_code` (`unit_code`),
  KEY `ix_organization_units_id` (`id`),
  KEY `organization_units_FK_0_0` (`parent_id`),
  CONSTRAINT `organization_units_FK_0_0` FOREIGN KEY (`parent_id`) REFERENCES `organization_units` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=10 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;


-- bnd_temp.employees definition

CREATE TABLE `employees` (
  `id` int NOT NULL AUTO_INCREMENT,
  `username` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `full_name` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `phone` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `dob` date DEFAULT NULL,
  `email` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `department_id` int DEFAULT NULL,
  `status` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `notes` text COLLATE utf8mb4_general_ci,
  `hourly_rate` int DEFAULT NULL,
  `allowance` int DEFAULT NULL,
  `password` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `role` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `is_locked` int DEFAULT NULL,
  `date_of_birth` date DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_employees_username` (`username`),
  KEY `ix_employees_id` (`id`),
  KEY `ix_employees_full_name` (`full_name`),
  KEY `employees_FK_0_0` (`department_id`),
  CONSTRAINT `employees_FK_0_0` FOREIGN KEY (`department_id`) REFERENCES `organization_units` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=111 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;