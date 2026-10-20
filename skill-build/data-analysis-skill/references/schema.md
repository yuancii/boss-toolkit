# orders 表字段字典

| 字段 | 类型 | 含义 | 备注 |
|---|---|---|---|
| id | INT | 订单号 | 自增主键 |
| category | VARCHAR(32) | 品类 | 手机 / 平板 / 耳机 |
| quantity | INT | 数量 | 正整数 |
| unit_price | DECIMAL(10,2) | 单价 | 人民币 |
| order_date | DATE | 下单日期 | 用于按天统计 |

## 常用口径
- 销售额 = quantity * unit_price
- 客单价 = 销售额 / 订单数
- 环比 = (本期 - 上期) / 上期
