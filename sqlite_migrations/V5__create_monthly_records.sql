CREATE TABLE monthly_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL,
    shift_code VARCHAR(50),
    date DATE,
    checkin_time TIME,
    checkout_time TIME,
    late_minutes INTEGER DEFAULT 0,
    early_minutes INTEGER DEFAULT 0,
    status INTEGER DEFAULT 0,
    explanation_reason TEXT,
    explanation_status INTEGER DEFAULT 0,
    note TEXT,
    FOREIGN KEY(employee_id) REFERENCES employees(id) ON DELETE CASCADE
);

CREATE INDEX idx_monthly_records_employee_id ON monthly_records(employee_id);
CREATE INDEX idx_monthly_records_date ON monthly_records(date);
