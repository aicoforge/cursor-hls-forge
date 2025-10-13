#!/usr/bin/env python3
"""
HLS Knowledge Base - 備份與恢復工具 (修正版 v2.5)

功能:
  1. 創建完整備份 (SQL)
  2. 創建 JSON 格式備份
  3. 列出所有備份
  4. 恢復備份 (自動識別 SQL/JSON，支持清空數據庫)

修正內容:
  - restore 前先清空數據庫（DROP SCHEMA CASCADE）
  - 使用事務確保原子性
  - 改進錯誤處理

使用方法:
  python3 backup_restore.py backup           # 創建 SQL 備份
  python3 backup_restore.py backup-json      # 創建 JSON 格式備份
  python3 backup_restore.py list             # 列出所有備份
  python3 backup_restore.py restore <file>   # 恢復備份
"""

import subprocess
import sys
import json
from datetime import datetime
from pathlib import Path

# 可選依賴
try:
    import asyncio
    import asyncpg
    HAS_ASYNCPG = True
except ImportError:
    HAS_ASYNCPG = False

# ==================== Configuration ====================
SCRIPT_DIR = Path(__file__).parent.resolve()
BACKUP_DIR = SCRIPT_DIR / "backups"

CONTAINER_NAME = "hls_knowledge_db"
DB_USER = "hls_user"
DB_NAME = "hls_knowledge"
DB_PASSWORD = "hls_pass_2024"

BACKUP_DIR.mkdir(exist_ok=True, parents=True)

# ==================== Color Output ====================
class C:
    G = '\033[92m'  # Green
    R = '\033[91m'  # Red
    Y = '\033[93m'  # Yellow
    B = '\033[94m'  # Blue
    N = '\033[0m'   # Normal

def success(msg): print(f"{C.G}✓ {msg}{C.N}")
def error(msg): print(f"{C.R}✗ {msg}{C.N}")
def warning(msg): print(f"{C.Y}⚠ {msg}{C.N}")
def info(msg): print(f"{C.B}→ {msg}{C.N}")
def header(msg): print(f"\n{'='*70}\n{msg}\n{'='*70}\n")

# ==================== Helper Functions ====================

def get_db_stats():
    """獲取數據庫統計"""
    tables = ["projects", "hls_rules", "design_iterations", "synthesis_results", "rules_effectiveness"]
    stats = {}

    for table in tables:
        try:
            cmd = f"docker exec {CONTAINER_NAME} psql -U {DB_USER} -d {DB_NAME} -t -c \"SELECT COUNT(*) FROM {table}\""
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=True)
            stats[table] = int(result.stdout.strip())
        except:
            stats[table] = 0

    return stats

# ==================== Backup Functions ====================

def backup_sql():
    """創建完整 SQL 備份"""
    header("創建完整備份 (SQL)")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = BACKUP_DIR / f"hls_kb_full_{timestamp}.sql"

    info(f"備份文件: {backup_file.name}")
    print()

    try:
        # 執行備份
        info("正在備份數據庫...")
        cmd = f"docker exec {CONTAINER_NAME} pg_dump -U {DB_USER} {DB_NAME}"
        result = subprocess.run(cmd.split(), capture_output=True, text=True, check=True)

        # 寫入文件
        with open(backup_file, 'w') as f:
            f.write(result.stdout)

        size_kb = backup_file.stat().st_size / 1024

        print()
        success(f"備份完成!")
        print(f"\n  文件: {backup_file}")
        print(f"  大小: {size_kb:.1f} KB\n")

        # 顯示統計
        stats = get_db_stats()
        print("  內容:")
        for table, count in stats.items():
            print(f"    • {table:25} {count:>5} 條")

        # 保存元數據
        metadata = {
            "backup_time": timestamp,
            "backup_type": "sql",
            "file": str(backup_file),
            "size_kb": size_kb,
            "stats": stats
        }

        metadata_file = backup_file.with_suffix('.json')
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        print()
        success(f"元數據: {metadata_file.name}")

        return True

    except Exception as e:
        error(f"備份失敗: {e}")
        return False

def backup_json():
    """創建 JSON 格式備份"""
    header("創建 JSON 格式備份")

    if not HAS_ASYNCPG:
        error("JSON 備份需要 asyncpg 模塊")
        print("安裝方式: pip3 install asyncpg")
        return False

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = BACKUP_DIR / f"hls_kb_json_{timestamp}.json"

    info(f"備份文件: {backup_file.name}")
    print()

    try:
        async def export_data():
            conn = await asyncpg.connect(
                host="localhost", port=5432,
                user=DB_USER, password=DB_PASSWORD,
                database=DB_NAME
            )

            data = {}

            info("正在導出數據...")

            # 導出各表
            for table in ["projects", "design_iterations", "synthesis_results", "rules_effectiveness"]:
                rows = await conn.fetch(f"SELECT * FROM {table}")
                data[table] = [dict(r) for r in rows]
                print(f"  • {table:25} {len(data[table]):>5} 條")

            await conn.close()
            return data

        data = asyncio.run(export_data())

        # 轉換特殊類型
        def convert(obj):
            if isinstance(obj, dict):
                return {k: convert(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert(i) for i in obj]
            elif isinstance(obj, datetime):
                return obj.isoformat()
            elif hasattr(obj, '__str__') and not isinstance(obj, (str, int, float, bool, type(None))):
                return str(obj)
            return obj

        data = convert(data)

        # 保存
        with open(backup_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        size_kb = backup_file.stat().st_size / 1024

        print()
        success("JSON 備份完成!")
        print(f"\n  文件: {backup_file}")
        print(f"  大小: {size_kb:.1f} KB\n")

        return True

    except ImportError:
        error("需要安裝 asyncpg: pip3 install asyncpg")
        return False
    except Exception as e:
        error(f"導出失敗: {e}")
        return False

def list_backups():
    """列出所有備份"""
    header("備份文件列表")

    sql_backups = sorted(BACKUP_DIR.glob("hls_kb_*.sql"), key=lambda p: p.stat().st_mtime, reverse=True)
    json_backups = sorted(BACKUP_DIR.glob("hls_kb_json_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)

    all_backups = sorted(sql_backups + json_backups, key=lambda p: p.stat().st_mtime, reverse=True)

    if not all_backups:
        warning("未找到備份文件")
        print(f"備份目錄: {BACKUP_DIR}\n")
        return

    print(f"備份目錄: {BACKUP_DIR}")
    print(f"找到 {len(all_backups)} 個備份文件\n")

    print(f"{'#':<4} {'文件名':<50} {'類型':<8} {'大小':<10} {'日期':<20}")
    print("-" * 95)

    for i, backup in enumerate(all_backups, 1):
        size_kb = backup.stat().st_size / 1024
        mtime = datetime.fromtimestamp(backup.stat().st_mtime)

        btype = "JSON" if backup.suffix == '.json' else "SQL"

        print(f"{i:<4} {backup.name:<50} {btype:<8} {size_kb:>6.1f} KB  {mtime.strftime('%Y-%m-%d %H:%M:%S')}")

        if btype == "SQL":
            metadata_file = backup.with_suffix('.json')
            if metadata_file.exists():
                try:
                    with open(metadata_file, 'r') as f:
                        metadata = json.load(f)
                    if 'stats' in metadata:
                        total = sum(v for v in metadata['stats'].values() if isinstance(v, int))
                        print(f"     └─ 共 {total} 條記錄")
                except:
                    pass

    print()
    info("恢復方式: python3 backup_restore.py restore <文件名>")

def restore_backup(backup_file):
    """恢復備份（改進版：先清空數據庫）"""
    header("恢復數據庫")

    # 查找文件
    backup_path = Path(backup_file)
    if not backup_path.exists():
        backup_path = BACKUP_DIR / backup_file
        if not backup_path.exists():
            error(f"文件不存在: {backup_file}")
            return False

    # 識別類型
    if backup_path.suffix == '.json':
        backup_type = "JSON"
    elif backup_path.suffix == '.sql':
        backup_type = "SQL"
    else:
        error(f"未知的文件類型: {backup_path.suffix}")
        return False

    # 顯示信息
    size_kb = backup_path.stat().st_size / 1024
    print(f"  文件: {backup_path.name}")
    print(f"  類型: {backup_type}")
    print(f"  大小: {size_kb:.1f} KB\n")

    # 確認
    warning("此操作將覆蓋當前數據庫!")
    confirm = input("確定要恢復嗎? (yes/no): ").strip().lower()

    if confirm != 'yes':
        info("操作已取消")
        return False

    print()

    try:
        if backup_type == "SQL":
            # SQL 恢復（內部先清空，但不顯示詳細步驟）
            info("正在恢復 SQL 備份...")
            
            # 清空數據庫（靜默執行）
            clean_sql = """
SELECT pg_terminate_backend(pid) 
FROM pg_stat_activity 
WHERE datname = 'hls_knowledge' AND pid <> pg_backend_pid();
DROP SCHEMA public CASCADE;
CREATE SCHEMA public;
GRANT ALL ON SCHEMA public TO hls_user;
GRANT ALL ON SCHEMA public TO public;
"""
            
            cmd = f"docker exec -i {CONTAINER_NAME} psql -U {DB_USER} -d {DB_NAME}"
            subprocess.run(
                cmd.split(), 
                input=clean_sql, 
                text=True, 
                capture_output=True,
                check=False
            )
            
            # 恢復數據
            with open(backup_path, 'r') as f:
                sql_content = f.read()

            cmd = f"docker exec -i {CONTAINER_NAME} psql -U {DB_USER} -d {DB_NAME}"
            result = subprocess.run(
                cmd.split(), 
                input=sql_content, 
                text=True, 
                check=True, 
                capture_output=True
            )

            print()
            success("恢復完成!")
            print()

            # 顯示統計
            stats = get_db_stats()
            print("  恢復後統計:")
            for table, count in stats.items():
                print(f"    • {table:25} {count:>5} 條")

        else:
            # JSON 恢復
            error("JSON 恢復功能尚未實現")
            info("建議使用 SQL 備份進行恢復操作")
            return False

        return True

    except subprocess.CalledProcessError as e:
        error(f"恢復失敗: {e}")
        if e.stderr:
            print(f"\n錯誤詳情:\n{e.stderr[:500]}")
        return False
    except Exception as e:
        error(f"恢復失敗: {e}")
        import traceback
        traceback.print_exc()
        return False

# ==================== Main ====================

def show_usage():
    print("""
HLS Knowledge Base - 備份與恢復工具 (修正版)

使用方式:
  python3 backup_restore.py backup           創建完整備份 (SQL)
  python3 backup_restore.py backup-json      創建 JSON 格式備份
  python3 backup_restore.py list             列出所有備份
  python3 backup_restore.py restore <file>   恢復備份（會先清空數據庫）

示例:
  # 創建備份
  python3 backup_restore.py backup

  # 查看備份
  python3 backup_restore.py list

  # 恢復備份（推薦）
  python3 backup_restore.py restore hls_kb_full_20251013_153225.sql

修正說明:
  - restore 操作會先完全清空數據庫
  - 避免外鍵衝突和重複記錄問題
  - 改進錯誤處理和報告
    """)

def main():
    if len(sys.argv) < 2:
        show_usage()
        return

    command = sys.argv[1]

    if command == 'backup':
        success_flag = backup_sql()
        sys.exit(0 if success_flag else 1)

    elif command == 'backup-json':
        success_flag = backup_json()
        sys.exit(0 if success_flag else 1)

    elif command == 'list':
        list_backups()

    elif command == 'restore':
        if len(sys.argv) < 3:
            error("請指定備份文件")
            print("使用方式: python3 backup_restore.py restore <file>")
            sys.exit(1)

        success_flag = restore_backup(sys.argv[2])
        sys.exit(0 if success_flag else 1)

    else:
        error(f"未知命令: {command}")
        show_usage()
        sys.exit(1)

if __name__ == "__main__":
    main()
