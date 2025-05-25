import sqlite3
import os

# 打印当前目录
print(f"当前工作目录: {os.getcwd()}")

try:
    # 连接到数据库
    db_path = 'data/db/economic_events.db'
    print(f"尝试连接数据库: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 查询所有表
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    print("数据库中的表:")
    for table in tables:
        print(f"- {table[0]}")
    
    # 获取economic_events表的结构
    if ('economic_events',) in tables:
        print("\neconomic_events表的结构:")
        cursor.execute("PRAGMA table_info(economic_events)")
        columns = cursor.fetchall()
        for col in columns:
            print(f"- {col[1]} ({col[2]})")
        
        # 获取数据总量
        cursor.execute("SELECT COUNT(*) FROM economic_events")
        count = cursor.fetchone()[0]
        print(f"\n表中共有 {count} 条记录")
        
        # 获取最新的几条记录
        if count > 0:
            print("\n最新的3条记录:")
            cursor.execute("SELECT * FROM economic_events ORDER BY id DESC LIMIT 3")
            recent_records = cursor.fetchall()
            for record in recent_records:
                print(record)
    
    conn.close()
    
except Exception as e:
    print(f"发生错误: {e}") 