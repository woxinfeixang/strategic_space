import sys

def print_first_and_last_line(file_path):
    try:
        with open(file_path, 'r') as f:
            first_line = f.readline()  # 标题行
            second_line = f.readline()  # 第一行数据
            
            # 回到文件开头
            f.seek(0)
            
            # 读取所有行并获取最后一行
            lines = f.readlines()
            last_line = lines[-1] if lines else None
            
            print(f"文件: {file_path}")
            print(f"标题行: {first_line.strip()}")
            print(f"第一行数据: {second_line.strip()}")
            print(f"最后一行数据: {last_line.strip() if last_line else 'None'}")
    except Exception as e:
        print(f"读取文件时出错: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python check_dates.py <文件路径>")
        sys.exit(1)
    
    file_path = sys.argv[1]
    print_first_and_last_line(file_path) 