---
name: order-data-analysis
description: 查询订单库并生成中文销售日报。当用户要求"统计销售额 / 出日报 / 看各品类"时使用。
version: 1.0.0
---

# 订单数据分析技能

## 何时使用
用户提出：统计销售额、按品类汇总、生成日报、对比两天的数据。

## 数据源
- 库：business，表：orders
- 字段：id / category / quantity / unit_price / order_date
- 销售额 = quantity * unit_price

## 执行步骤
1. 把需求翻译成只读 SQL（只允许 SELECT，不加分号，默认 LIMIT 200）；
2. 调用工具 query_sql 执行；
3. 按 references/report_template.md 的格式输出；
4. 若某品类环比下跌超过 20%，在【异常】中单独提示。

## 约束
- 禁止 DELETE / UPDATE / DROP；
- 查不到数据时回答"无数据"，不得编造；
- 金额保留两位小数，按销售额降序。

## 示例
用户：统计昨天各品类销售额
SQL：SELECT category, SUM(quantity*unit_price) AS sales
     FROM orders
     WHERE order_date = CURDATE() - INTERVAL 1 DAY
     GROUP BY category
     ORDER BY sales DESC
输出：三行明细 + 一句话结论。
