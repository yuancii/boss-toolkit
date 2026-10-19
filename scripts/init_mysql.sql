-- MySQL 8.4 初始化脚本（本项目 tools_mysql.py / daily_report.py 的测试库）
-- 用法：
--   mysql -u root -p < scripts/init_mysql.sql
-- 说明：
--   1. 建库 business（utf8mb4）、表 orders、5 条样例订单；
--   2. 建只读账号 reader / readonly123（仅用于本地演示，生产请换成强密码）；
--   3. 样例订单日期用 CURDATE() 相对值，保证"昨天/前天"总有数据。

CREATE DATABASE IF NOT EXISTS business CHARACTER SET utf8mb4;
USE business;

CREATE TABLE IF NOT EXISTS orders (
  id INT PRIMARY KEY AUTO_INCREMENT,
  category VARCHAR(32) NOT NULL,
  quantity INT NOT NULL,
  unit_price DECIMAL(10,2) NOT NULL,
  order_date DATE NOT NULL,
  KEY idx_order_date (order_date)
);

-- 避免重复执行脚本时插入重复数据
DELETE FROM orders;

INSERT INTO orders (category, quantity, unit_price, order_date) VALUES
('手机', 1, 3999.00, CURDATE() - INTERVAL 1 DAY),
('手机', 2, 3999.00, CURDATE() - INTERVAL 1 DAY),
('耳机', 3,  299.00, CURDATE() - INTERVAL 1 DAY),
('平板', 2, 2599.00, CURDATE() - INTERVAL 1 DAY),
('平板', 1, 2599.00, CURDATE() - INTERVAL 2 DAY);

-- 只读账号（localhost 与 % 都建，避免客户端匹配不到）
CREATE USER IF NOT EXISTS 'reader'@'localhost' IDENTIFIED BY 'readonly123';
CREATE USER IF NOT EXISTS 'reader'@'%'         IDENTIFIED BY 'readonly123';
GRANT SELECT ON business.* TO 'reader'@'localhost';
GRANT SELECT ON business.* TO 'reader'@'%';
FLUSH PRIVILEGES;

-- 自检：各品类销售额（应输出 手机 11997.00 / 平板 7797.00 / 耳机 897.00）
SELECT category, SUM(quantity * unit_price) AS sales
FROM orders
GROUP BY category
ORDER BY sales DESC;
