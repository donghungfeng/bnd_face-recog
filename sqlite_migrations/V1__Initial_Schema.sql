-- app_configs definition
CREATE TABLE app_configs (
    config_key VARCHAR(50) NOT NULL, 
    config_value VARCHAR(255) NOT NULL, 
    description VARCHAR(255), 
    updated_at DATETIME, 
    PRIMARY KEY (config_key)
);
CREATE INDEX ix_app_configs_config_key ON app_configs (config_key);

-- attendance definition
CREATE TABLE attendance (
    id INTEGER NOT NULL,
    username VARCHAR,
    full_name VARCHAR,
    check_in_time DATETIME,
    image_path VARCHAR,
    late_minutes INTEGER,
    early_minutes INTEGER,
    explanation_status VARCHAR,
    explanation_reason TEXT,
    confidence REAL, 
    is_fraud INTEGER DEFAULT 0, 
    fraud_note TEXT, 
    client_ip TEXT, 
    latitude REAL, 
    longitude REAL, 
    attendance_type TEXT DEFAULT 'Tập trung', 
    note TEXT, -- ĐÃ SỬA: Bỏ chữ INTEGER thừa ở đây
    CONSTRAINT ATTENDANCE_PK PRIMARY KEY (id)
);

-- leave_requests definition
CREATE TABLE leave_requests (
    id INTEGER NOT NULL, 
    username VARCHAR, 
    full_name VARCHAR, 
    leave_date DATE, 
    reason VARCHAR, 
    approver VARCHAR, 
    status VARCHAR, 
    PRIMARY KEY (id)
);
CREATE INDEX ix_leave_requests_username ON leave_requests (username);
CREATE INDEX ix_leave_requests_leave_date ON leave_requests (leave_date);
CREATE INDEX ix_leave_requests_id ON leave_requests (id);

-- shift_assignments definition
CREATE TABLE shift_assignments (
    id INTEGER NOT NULL, 
    username VARCHAR, 
    shift_code VARCHAR, 
    shift_date DATE, 
    PRIMARY KEY (id)
);
CREATE INDEX ix_shift_assignments_id ON shift_assignments (id);
CREATE INDEX ix_shift_assignments_shift_date ON shift_assignments (shift_date);
CREATE INDEX ix_shift_assignments_username ON shift_assignments (username);
CREATE INDEX ix_shift_assignments_shift_code ON shift_assignments (shift_code);

-- shift_categories definition
CREATE TABLE shift_categories (
    id INTEGER NOT NULL, 
    shift_code VARCHAR, 
    shift_name VARCHAR, 
    start_time TIME, 
    end_time TIME, 
    is_overnight INTEGER, 
    status VARCHAR, 
    notes TEXT, 
    PRIMARY KEY (id)
);
CREATE INDEX ix_shift_categories_id ON shift_categories (id);
CREATE UNIQUE INDEX ix_shift_categories_shift_code ON shift_categories (shift_code);

-- organization_units definition
CREATE TABLE organization_units (
    id INTEGER NOT NULL, 
    unit_code VARCHAR, 
    unit_name VARCHAR, 
    unit_type VARCHAR, 
    parent_id INTEGER, 
    order_num INTEGER, 
    level INTEGER, 
    location VARCHAR, 
    status VARCHAR, 
    notes TEXT, 
    PRIMARY KEY (id), 
    FOREIGN KEY(parent_id) REFERENCES organization_units (id)
);
CREATE UNIQUE INDEX ix_organization_units_unit_code ON organization_units (unit_code);
CREATE INDEX ix_organization_units_id ON organization_units (id);

-- employees definition
CREATE TABLE employees (
    id INTEGER NOT NULL, 
    username VARCHAR, 
    full_name VARCHAR, 
    phone VARCHAR, 
    dob DATE, 
    email VARCHAR, 
    department_id INTEGER, 
    status VARCHAR, 
    notes TEXT, 
    hourly_rate INTEGER, 
    allowance INTEGER, 
    password VARCHAR, 
    role VARCHAR, 
    is_locked INTEGER, 
    date_of_birth DATE, 
    PRIMARY KEY (id), 
    FOREIGN KEY(department_id) REFERENCES organization_units (id)
);
CREATE INDEX ix_employees_full_name ON employees (full_name);
CREATE INDEX ix_employees_id ON employees (id);
CREATE UNIQUE INDEX ix_employees_username ON employees (username);