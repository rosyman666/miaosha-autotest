@echo off
rem 重置秒杀数据到干净基线（跑 -m miaosha_write 前执行）
rem 请按自己的环境修改下面四个变量
set MYSQL=D:\mysql\bin\mysql.exe
set REDIS=D:\Redis\redis-cli.exe
set DB_USER=root
set DB_PASS=123456

%MYSQL% -u%DB_USER% -p%DB_PASS% -D miaosha -e "DELETE FROM miaosha_order WHERE goods_id=1; DELETE FROM order_info WHERE goods_id=1; UPDATE miaosha_goods SET stock_count=10 WHERE goods_id=1;"
%REDIS% -h 127.0.0.1 -p 6379 set GoodsKey:gs1 10
%REDIS% -h 127.0.0.1 -p 6379 del "OrderKey:moug13000000000_1"
%REDIS% -h 127.0.0.1 -p 6379 del "MiaoshaKey:mp13000000000_1"
echo.
echo 数据已重置：库存 10，订单清零，Redis 缓存清理
pause
