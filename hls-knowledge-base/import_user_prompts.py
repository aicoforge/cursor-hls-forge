#!/usr/bin/env python3
"""
HLS Knowledge Base - User Prompts 導入工具
從 user_prompts.txt 解析並導入用戶提示到資料庫
"""

import asyncio
import asyncpg
import re
from uuid import uuid4
from typing import List, Dict
from pathlib import Path

DATABASE_URL = "postgresql://hls_user:hls_pass_2024@localhost:5432/hls_knowledge"

# 關鍵字到 category 的映射
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
    'loop': 'optimization',
    'cordic': 'algorithm',
    'fir': 'algorithm',
}

def parse_prompts_from_file(filepath: str) -> List[Dict]:
    """
    從 user_prompts.txt 解析用戶提示
    格式: - [P001] Prompt text...
    """
    print(f"[1/4] 解析 {filepath}...")
    
    if not Path(filepath).exists():
        print(f"✗ 文件不存在: {filepath}")
        return []
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    prompts = []
    current_section = 'general'
    line_number = 0
    
    lines = content.split('\n')
    
    for line in lines:
        line_number += 1
        stripped = line.strip()
        
        # 跳過空行和元數據行
        if not stripped or stripped == '---' or stripped.startswith('alwaysApply:'):
            continue
        
        # 識別分類標題（# FIR Optimization Prompts）
        if stripped.startswith('# ') and not stripped.startswith('# User Prompts'):
            section_name = stripped[2:].strip().lower()
            # 提取關鍵字作為 category
            if 'fir' in section_name:
                current_section = 'algorithm'
            elif 'cordic' in section_name:
                current_section = 'algorithm'
            elif 'loop' in section_name:
                current_section = 'optimization'
            elif 'memory' in section_name:
                current_section = 'memory'
            elif 'interface' in section_name:
                current_section = 'interface'
            else:
                current_section = 'general'
            continue
        
        # 解析提示行（以 "- [P###]" 開頭）
        if stripped.startswith('- [P') and ']' in stripped:
            # 提取 [P001]
            end_bracket = stripped.index(']')
            prompt_code = stripped[3:end_bracket]  # 去掉 "- ["
            
            # 提取提示文本
            prompt_text = stripped[end_bracket + 1:].strip()
            
            if len(prompt_text) < 10:
                continue
            
            # 根據關鍵字確定分類
            category = current_section
            prompt_lower = prompt_text.lower()
            for keyword, cat in KEYWORD_TO_CATEGORY.items():
                if keyword in prompt_lower:
                    category = cat
                    break
            
            # 確定優先級（用戶提示通常優先級稍低）
            priority = 6  # 默認
            
            if any(kw in prompt_lower for kw in ['always', 'must', 'critical']):
                priority = 8
            elif any(kw in prompt_lower for kw in ['should', 'recommend', 'consider']):
                priority = 6
            elif any(kw in prompt_lower for kw in ['may', 'optional', 'can']):
                priority = 5
            
            # 提取來源（從註釋中）
            source = 'user_experience'
            if 'fir' in current_section.lower():
                source = 'FIR optimization experience'
            elif 'cordic' in current_section.lower():
                source = 'CORDIC optimization experience'
            
            prompts.append({
                'prompt_code': prompt_code,
                'prompt_text': prompt_text,
                'category': category,
                'priority': priority,
                'source': source,
                'description': f'User prompt {line_number} from user_prompts.txt'
            })
    
    print(f"✓ 解析完成，找到 {len(prompts)} 條用戶提示\n")
    
    # 顯示分類統計
    category_stats = {}
    for prompt in prompts:
        cat = prompt['category']
        category_stats[cat] = category_stats.get(cat, 0) + 1
    
    print("分類預覽:")
    for cat, count in sorted(category_stats.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {count} 條提示")
    print()
    
    return prompts

async def import_prompts_to_db(prompts: List[Dict], mode: str = 'upsert'):
    """
    導入用戶提示到資料庫（作為 rule_type='user_prompt'）
    
    mode:
    - 'upsert': 更新已存在的提示（默認）
    - 'skip': 跳過已存在的提示
    - 'replace': 刪除所有用戶提示後重新導入
    """
    print(f"[2/4] 導入用戶提示到資料庫 (模式: {mode})...")
    
    conn = await asyncpg.connect(DATABASE_URL)
    
    try:
        # 如果是 replace 模式，先清空用戶提示
        if mode == 'replace':
            print("  清空現有用戶提示...")
            await conn.execute("""
                DELETE FROM rules_effectiveness 
                WHERE rule_id IN (
                    SELECT id FROM hls_rules WHERE rule_type = 'user_prompt'
                )
            """)
            await conn.execute("DELETE FROM hls_rules WHERE rule_type = 'user_prompt'")
            print("  ✓ 已清空\n")
        
        inserted = 0
        updated = 0
        skipped = 0
        
        for prompt in prompts:
            try:
                # 檢查是否已存在（優先用 rule_code 查找）
                existing_id = await conn.fetchval(
                    "SELECT id FROM hls_rules WHERE rule_code = $1",
                    prompt['prompt_code']
                )
                
                if existing_id:
                    if mode == 'skip':
                        skipped += 1
                        continue
                    elif mode == 'upsert':
                        # 更新現有提示
                        await conn.execute("""
                            UPDATE hls_rules
                            SET rule_text = $1, category = $2, priority = $3, 
                                description = $4, source = $5
                            WHERE id = $6
                        """, prompt['prompt_text'], prompt['category'], 
                            prompt['priority'], prompt['description'],
                            prompt['source'], existing_id)
                        updated += 1
                else:
                    # 插入新提示
                    await conn.execute("""
                        INSERT INTO hls_rules (
                            id, rule_code, rule_type, rule_text, 
                            category, priority, description, source
                        ) VALUES ($1, $2, 'user_prompt', $3, $4, $5, $6, $7)
                    """, uuid4(), prompt['prompt_code'], prompt['prompt_text'],
                        prompt['category'], prompt['priority'], 
                        prompt['description'], prompt['source'])
                    inserted += 1
                
            except Exception as e:
                print(f"  ✗ 錯誤: {prompt['prompt_text'][:50]}... ({e})")
                skipped += 1
        
        print(f"\n{'='*60}")
        print(f"✓ 成功插入 {inserted} 條新提示")
        if updated > 0:
            print(f"✓ 成功更新 {updated} 條已存在提示")
        if skipped > 0:
            print(f"✗ 跳過 {skipped} 條提示")
        print(f"{'='*60}\n")
        
    finally:
        await conn.close()

async def verify_import():
    """驗證導入結果"""
    print("[3/4] 驗證導入結果...")
    
    conn = await asyncpg.connect(DATABASE_URL)
    
    try:
        # 統計
        stats = await conn.fetchrow("""
            SELECT 
                COUNT(*) FILTER (WHERE rule_type = 'official') as official_count,
                COUNT(*) FILTER (WHERE rule_type = 'user_prompt') as prompt_count,
                COUNT(*) as total_count
            FROM hls_rules
        """)
        
        print(f"  總規則數: {stats['total_count']}")
        print(f"  官方規則 (R###): {stats['official_count']}")
        print(f"  用戶提示 (P###): {stats['prompt_count']}")
        print()
        
        # 顯示用戶提示示例
        prompts = await conn.fetch("""
            SELECT rule_code, rule_text, category, source
            FROM hls_rules
            WHERE rule_type = 'user_prompt'
            ORDER BY rule_code
            LIMIT 5
        """)
        
        print("  用戶提示示例:")
        for p in prompts:
            print(f"  {p['rule_code']}: {p['rule_text'][:50]}...")
            print(f"       Category: {p['category']}, Source: {p['source']}")
        
        print()
        
    finally:
        await conn.close()

async def main():
    """主函數"""
    print("=" * 60)
    print("HLS Knowledge Base - User Prompts 導入工具")
    print("=" * 60)
    print()
    
    # 1. 解析文件
    prompts = parse_prompts_from_file("user_prompts.txt")
    
    if not prompts:
        print("沒有提示可導入，程序退出")
        return
    
    # 2. 導入到資料庫
    try:
        await import_prompts_to_db(prompts, mode='upsert')
    except Exception as e:
        print(f"✗ 資料庫連接錯誤: {e}")
        print("請確保 PostgreSQL 服務已啟動")
        return
    
    # 3. 驗證結果
    try:
        await verify_import()
    except Exception as e:
        print(f"✗ 驗證錯誤: {e}")
    
    print("=" * 60)
    print("✓ 所有操作完成!")
    print("=" * 60)
    print("\n提示:")
    print("  - 官方規則 (R###) 不會被修改")
    print("  - 用戶提示 (P###) 可以隨時添加或更新")
    print("  - 查詢: curl 'http://localhost:8000/api/rules/effective?rule_type=user_prompt'")

if __name__ == "__main__":
    asyncio.run(main())

