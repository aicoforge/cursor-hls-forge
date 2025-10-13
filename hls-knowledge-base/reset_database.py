#!/usr/bin/env python3
"""
HLS Knowledge Base - 資料庫重置工具
用於清理所有數據並重新初始化
"""

import asyncio
import asyncpg
import sys

DATABASE_URL = "postgresql://hls_user:hls_pass_2024@localhost:5432/hls_knowledge"

async def reset_database(confirm: bool = False):
    """重置資料庫（清空所有數據）"""
    
    if not confirm:
        print("=" * 60)
        print("⚠️  警告: 此操作將刪除所有數據!")
        print("=" * 60)
        print("\n將清空以下表格:")
        print("  - rules_effectiveness")
        print("  - synthesis_results")
        print("  - design_iterations")
        print("  - design_patterns")
        print("  - projects")
        print("  - hls_rules")
        print()
        
        response = input("確定要繼續嗎? (yes/no): ").strip().lower()
        if response not in ['yes', 'y']:
            print("操作已取消")
            return False
    
    print("\n開始重置資料庫...")
    
    conn = await asyncpg.connect(DATABASE_URL)
    
    try:
        # 按照依賴順序刪除數據
        tables = [
            'rules_effectiveness',
            'synthesis_results',
            'design_iterations',
            'design_patterns',
            'projects',
            'hls_rules'
        ]
        
        for table in tables:
            count = await conn.fetchval(f"SELECT COUNT(*) FROM {table}")
            await conn.execute(f"DELETE FROM {table}")
            print(f"  ✓ 清空 {table} ({count} 條記錄)")
        
        print("\n✓ 資料庫已重置!")
        print("\n下一步:")
        print("  1. 運行 import_hls_rules.py 導入規則")
        print("  2. (可選) 運行 import_fir128_data.py 導入示例數據")
        
        return True
        
    except Exception as e:
        print(f"\n✗ 錯誤: {e}")
        return False
    
    finally:
        await conn.close()

async def show_stats():
    """顯示當前資料庫統計"""
    print("=" * 60)
    print("當前資料庫統計")
    print("=" * 60)
    
    conn = await asyncpg.connect(DATABASE_URL)
    
    try:
        stats = {
            'projects': await conn.fetchval("SELECT COUNT(*) FROM projects"),
            'hls_rules': await conn.fetchval("SELECT COUNT(*) FROM hls_rules"),
            'design_iterations': await conn.fetchval("SELECT COUNT(*) FROM design_iterations"),
            'synthesis_results': await conn.fetchval("SELECT COUNT(*) FROM synthesis_results"),
            'rules_effectiveness': await conn.fetchval("SELECT COUNT(*) FROM rules_effectiveness"),
            'design_patterns': await conn.fetchval("SELECT COUNT(*) FROM design_patterns")
        }
        
        print()
        for table, count in stats.items():
            print(f"  {table:<25} {count:>10} 條記錄")
        print()
        
        total = sum(stats.values())
        if total == 0:
            print("  資料庫為空,可以開始導入數據")
        else:
            print(f"  總計: {total} 條記錄")
        print()
        
    finally:
        await conn.close()

async def main():
    """主函數"""
    if len(sys.argv) > 1 and sys.argv[1] == '--stats':
        # 只顯示統計
        await show_stats()
        return
    
    # 先顯示統計
    await show_stats()
    
    # 執行重置
    success = await reset_database()
    
    if success:
        # 重置後再次顯示統計
        print()
        await show_stats()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n操作已取消")
