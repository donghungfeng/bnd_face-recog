CREATE TABLE wifi (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(255) NOT NULL,
    password VARCHAR(255) NOT NULL,
    location VARCHAR(255),
    ip_address VARCHAR(45),
    note TEXT,
    status VARCHAR(50) NOT NULL
);