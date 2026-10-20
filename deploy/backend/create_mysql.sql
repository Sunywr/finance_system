-- 在 MySQL 8 上以 root 执行；请先替换 CHANGE_ME。
CREATE DATABASE IF NOT EXISTS finance
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;

CREATE USER IF NOT EXISTS 'finance_app'@'localhost' IDENTIFIED BY 'CHANGE_ME';
CREATE USER IF NOT EXISTS 'finance_app'@'127.0.0.1' IDENTIFIED BY 'CHANGE_ME';

GRANT ALL PRIVILEGES ON finance.* TO 'finance_app'@'localhost';
GRANT ALL PRIVILEGES ON finance.* TO 'finance_app'@'127.0.0.1';
GRANT ALL PRIVILEGES ON test_finance.* TO 'finance_app'@'localhost';
GRANT ALL PRIVILEGES ON test_finance.* TO 'finance_app'@'127.0.0.1';
FLUSH PRIVILEGES;
