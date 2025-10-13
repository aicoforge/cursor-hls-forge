#!/usr/bin/env python3
"""
HLS Knowledge Base - 規則導入工具（改進版）
- 從 ug1399_rules.txt 解析規則
- 自動去除 "-" 前綴
- 支持重複執行（UPSERT）
- 根據大類和關鍵字精確分類
"""

import asyncio
import asyncpg
import re
from uuid import uuid4
from typing import List, Dict, Optional
from pathlib import Path

DATABASE_URL = "postgresql://hls_user:hls_pass_2024@localhost:5432/hls_knowledge"

# 大類到 category 的映射
SECTION_TO_CATEGORY = {
    'dataflow': 'dataflow',
    'pipeline': 'pipeline',
    'hierarchical design': 'hierarchical',
    'data types': 'data_types',
    'structural design': 'structural',
    'control i/o handling': 'interface',
}

# 關鍵字到 category 的映射（用於細化分類）
KEYWORD_TO_CATEGORY = {
    'pipeline': 'pipeline',
    'dataflow': 'dataflow',
    'stream': 'dataflow',
    'fifo': 'dataflow',
    'array_partition': 'memory',
    'partition': 'memory',
    'memory': 'memory',
    'bram': 'memory',
    'unroll': 'optimization',
    'inline': 'optimization',
    'flatten': 'optimization',
    'merge': 'optimization',
    'interface': 'interface',
    'axis': 'interface',
    'm_axi': 'interface',
    's_axilite': 'interface',
    'ap_ctrl': 'interface',
    'resource': 'resource',
    'dsp': 'resource',
    'lut': 'resource',
    'dependence': 'analysis',
}

def parse_rules_from_file(filepath: str) -> List[Dict]:
    """
    解析 ug1399_rules.txt 文件
    
    返回格式:
    [
        {
            'rule_text': '規則文本（已去除 - 前綴）',
            'category': 'pipeline',
            'priority': 9,
            'description': '來源描述'
        },
        ...
    ]
    """
    print(f"[1/4] 解析 {filepath}...")
    
    if not Path(filepath).exists():
        print(f"✗ 錯誤: 找不到文件 {filepath}")
        print("請確保 ug1399_rules.txt 在當前目錄\n")
        return []
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"✗ 讀取文件錯誤: {e}\n")
        return []
    
    rules = []
    current_section = None
    line_number = 0
    
    lines = content.split('\n')
    
    for line in lines:
        line_number += 1
        stripped = line.strip()
        
        # 跳過空行和元數據行
        if not stripped or stripped == '---' or stripped.startswith('alwaysApply:'):
            continue
        
        # 識別大類標題（# Dataflow, # Pipeline 等）
        if stripped.startswith('# '):
            section_name = stripped[2:].strip().lower()
            current_section = SECTION_TO_CATEGORY.get(section_name, 'general')
            continue
        
        # 解析規則行（以 "- " 開頭）
        if stripped.startswith('- '):
            # 去除 "- " 前綴
            rule_text = stripped[2:].strip()
            
            # 跳過太短的規則
            if len(rule_text) < 10:
                continue
            
            # 提取規則編號（如果有）[R001] 格式
            rule_code = None
            if rule_text.startswith('[R') and ']' in rule_text:
                # 提取 [R001]
                end_bracket = rule_text.index(']')
                rule_code = rule_text[1:end_bracket]  # 去掉 [ 和 ]
                # 提取實際規則文本
                rule_text = rule_text[end_bracket + 1:].strip()
            
            # 確定分類（優先使用大類，然後根據關鍵字細化）
            category = current_section if current_section else 'general'
            
            # 根據關鍵字細化分類
            rule_lower = rule_text.lower()
            for keyword, cat in KEYWORD_TO_CATEGORY.items():
                if keyword in rule_lower:
                    category = cat
                    break
            
            # 確定優先級（基於關鍵詞）
            priority = 5  # 默認
            
            if any(kw in rule_lower for kw in ['always', 'must', 'critical', 'never']):
                priority = 9
            elif any(kw in rule_lower for kw in ['do not', 'avoid', 'ensure']):
                priority = 7
            elif any(kw in rule_lower for kw in ['should', 'recommend', 'prefer']):
                priority = 7
            elif any(kw in rule_lower for kw in ['consider', 'may', 'optional']):
                priority = 4
            
            rules.append({
                'rule_code': rule_code,
                'rule_text': rule_text,
                'category': category,
                'priority': priority,
                'description': f'Rule {line_number} from ug1399_rules.txt'
            })
    
    print(f"✓ 解析完成,找到 {len(rules)} 條規則\n")
    
    # 顯示分類統計
    category_stats = {}
    for rule in rules:
        cat = rule['category']
        category_stats[cat] = category_stats.get(cat, 0) + 1
    
    print("分類預覽:")
    for cat, count in sorted(category_stats.items(), key=lambda x: x[1], reverse=True):
        print(f"  {cat}: {count} 條規則")
    print()
    
    return rules

async def import_rules_to_db(rules: List[Dict], mode: str = 'upsert'):
    """
    導入規則到資料庫
    
    mode:
    - 'upsert': 更新已存在的規則（默認）
    - 'skip': 跳過已存在的規則
    - 'replace': 刪除所有規則後重新導入
    """
    print(f"[2/4] 導入規則到資料庫 (模式: {mode})...")
    
    conn = await asyncpg.connect(DATABASE_URL)
    
    try:
        # 如果是 replace 模式，先清空表
        if mode == 'replace':
            print("  清空現有規則...")
            await conn.execute("DELETE FROM rules_effectiveness")
            await conn.execute("DELETE FROM hls_rules")
            print("  ✓ 已清空\n")
        
        inserted = 0
        updated = 0
        skipped = 0
        
        for rule in rules:
            try:
                # 檢查是否已存在（優先用 rule_code 查找）
                existing_id = None
                if rule.get('rule_code'):
                    existing_id = await conn.fetchval(
                        "SELECT id FROM hls_rules WHERE rule_code = $1",
                        rule['rule_code']
                    )
                
                # 如果沒找到，用 rule_text 查找
                if not existing_id:
                    existing_id = await conn.fetchval(
                        "SELECT id FROM hls_rules WHERE rule_text = $1",
                        rule['rule_text']
                    )
                
                if existing_id:
                    if mode == 'skip':
                        skipped += 1
                        continue
                    elif mode == 'upsert':
                        # 更新現有規則（包含 rule_code，保留 rule_type）
                        await conn.execute("""
                            UPDATE hls_rules
                            SET rule_code = $1, category = $2, priority = $3, description = $4, source = 'UG1399'
                            WHERE id = $5
                        """, rule.get('rule_code'), rule['category'], rule['priority'], 
                            rule['description'], existing_id)
                        updated += 1
                else:
                    # 插入新規則
                    await conn.execute("""
                        INSERT INTO hls_rules (id, rule_code, rule_type, rule_text, category, priority, description, source)
                        VALUES ($1, $2, 'official', $3, $4, $5, $6, 'UG1399')
                    """, uuid4(), rule.get('rule_code'), rule['rule_text'], rule['category'],
                        rule['priority'], rule['description'])
                    inserted += 1
                
            except Exception as e:
                print(f"  ✗ 錯誤: {rule['rule_text'][:50]}... ({e})")
                skipped += 1
        
        print(f"\n{'='*60}")
        print(f"✓ 成功插入 {inserted} 條新規則")
        if updated > 0:
            print(f"✓ 成功更新 {updated} 條已存在規則")
        if skipped > 0:
            print(f"✗ 跳過 {skipped} 條規則")
        print(f"{'='*60}\n")
        
        # 顯示最終統計
        stats = await conn.fetch("""
            SELECT category, COUNT(*) as count, 
                   ROUND(AVG(priority), 2) as avg_priority
            FROM hls_rules
            GROUP BY category
            ORDER BY count DESC
        """)
        
        print("資料庫中的規則統計:")
        print(f"{'類別':<20} {'數量':<10} {'平均優先級':<15}")
        print("-" * 60)
        for row in stats:
            print(f"{row['category']:<20} {row['count']:<10} {row['avg_priority']:<15}")
        
        total = await conn.fetchval("SELECT COUNT(*) FROM hls_rules")
        print("-" * 60)
        print(f"{'總計':<20} {total:<10}")
        print()
        
    finally:
        await conn.close()

async def verify_import():
    """驗證導入結果"""
    print("[3/4] 驗證導入結果...")
    
    conn = await asyncpg.connect(DATABASE_URL)
    
    try:
        # 檢查總數
        total = await conn.fetchval("SELECT COUNT(*) FROM hls_rules")
        print(f"  總規則數: {total}")
        
        # 檢查高優先級規則
        high_priority = await conn.fetch("""
            SELECT category, rule_text
            FROM hls_rules
            WHERE priority >= 9
            ORDER BY category, rule_text
            LIMIT 10
        """)
        
        print(f"\n  前 10 條高優先級規則 (priority >= 9):")
        for i, rule in enumerate(high_priority, 1):
            preview = rule['rule_text'][:70]
            if len(rule['rule_text']) > 70:
                preview += "..."
            print(f"  {i}. [{rule['category']}] {preview}")
        
        # 檢查每個類別的規則數量
        category_dist = await conn.fetch("""
            SELECT category, COUNT(*) as count
            FROM hls_rules
            GROUP BY category
            ORDER BY count DESC
        """)
        
        print(f"\n  類別分布:")
        for row in category_dist:
            bar = "█" * min(row['count'] // 5, 50)
            print(f"    {row['category']:<20} {bar} ({row['count']})")
        
        print()
        
    finally:
        await conn.close()

async def export_summary(output_file: str = "import_summary.txt"):
    """導出導入摘要"""
    print("[4/4] 生成導入摘要...")
    
    conn = await asyncpg.connect(DATABASE_URL)
    
    try:
        stats = await conn.fetch("""
            SELECT 
                category,
                COUNT(*) as rule_count,
                MIN(priority) as min_priority,
                MAX(priority) as max_priority,
                ROUND(AVG(priority), 2) as avg_priority
            FROM hls_rules
            GROUP BY category
            ORDER BY rule_count DESC
        """)
        
        total = await conn.fetchval("SELECT COUNT(*) FROM hls_rules")
        
        # 寫入摘要文件
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("HLS Knowledge Base - Import Summary\n")
            f.write("=" * 60 + "\n\n")
            f.write(f"Total Rules: {total}\n\n")
            f.write("Category Statistics:\n")
            f.write("-" * 60 + "\n")
            f.write(f"{'Category':<20} {'Count':<10} {'Priority Range':<20} {'Avg':<10}\n")
            f.write("-" * 60 + "\n")
            
            for row in stats:
                f.write(f"{row['category']:<20} {row['rule_count']:<10} "
                       f"{row['min_priority']}-{row['max_priority']:<17} "
                       f"{row['avg_priority']:<10}\n")
            
            f.write("-" * 60 + "\n")
        
        print(f"✓ 摘要已保存到: {output_file}\n")
        
    finally:
        await conn.close()

async def main():
    """主函數"""
    print("=" * 60)
    print("HLS Knowledge Base - 規則導入工具（改進版）")
    print("=" * 60)
    print()
    
    # 1. 解析文件
    rules = parse_rules_from_file("ug1399_rules.txt")
    
    if not rules:
        print("沒有規則可導入,程序退出")
        return
    
    # 2. 導入到資料庫（使用 upsert 模式支持重複執行）
    try:
        await import_rules_to_db(rules, mode='upsert')
    except Exception as e:
        print(f"✗ 資料庫連接錯誤: {e}")
        print("請確保 PostgreSQL 服務已啟動")
        return
    
    # 3. 驗證結果
    try:
        await verify_import()
    except Exception as e:
        print(f"✗ 驗證錯誤: {e}")
    
    # 4. 生成摘要
    try:
        await export_summary()
    except Exception as e:
        print(f"✗ 摘要生成錯誤: {e}")
    
    print("=" * 60)
    print("✓ 所有操作完成!")
    print("=" * 60)
    print("\n下一步:")
    print("  1. 啟動 API 服務: docker-compose up -d")
    print("  2. 測試 API: curl http://localhost:8000/health")
    print("  3. 查看規則: curl http://localhost:8000/api/rules/effective")

if __name__ == "__main__":
    asyncio.run(main())
