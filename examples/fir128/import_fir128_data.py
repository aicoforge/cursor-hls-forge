#!/usr/bin/env python3
"""
HLS Knowledge Base - FIR128 數據導入工具（包含規則效果記錄）

版本: v1.0
更新日期: 2025-10-13

功能:
- 導入三次迭代的完整設計記錄
- 記錄規則應用效果到 rules_effectiveness

UPSERT 模式（覆蓋策略）:
- 使用 (project_id, iteration_number) 查詢現有記錄
- 如果已存在 → UPDATE（覆蓋）
- 如果不存在 → INSERT（新增）

重複執行行為:
- projects: 覆蓋項目信息
- design_iterations: 覆蓋 Iteration #1, #2, #3
- synthesis_results: 覆蓋對應的綜合結果
- rules_effectiveness: 覆蓋統計值（不累加）
- 未在腳本中的記錄（如 Iteration #4）: 保留不變

適用場景:
- 數據修正/初始化
- 更新 code_snapshot 注釋
- 修正綜合結果數值

注意:
- rules_effectiveness 覆蓋模式只適用於本腳本
- API 自動記錄使用累加模式（真實統計）
"""

import asyncio
import asyncpg
import json
import re
import hashlib  # 用於計算 code_snapshot 的 SHA256 hash
from uuid import UUID, uuid4
from datetime import datetime, timedelta

DATABASE_URL = "postgresql://hls_user:hls_pass_2024@localhost:5432/hls_knowledge"

# ⚠️ 注意: 
# - project_id 保持固定（用於識別同一個項目的所有迭代）
# - iteration_id 使用 (project_id, iteration_number) 查詢現有記錄
# - 已存在則使用現有 UUID 並覆蓋內容，不存在則生成新 UUID

# FIR128 三次迭代數據（與用戶提供的實驗結果一致）
FIR128_DATA = {
    "project": {
        "id": "550e8400-e29b-41d4-a716-446655440001",  # 項目 ID 固定
        "name": "FIR128_Optimization_Demo",
        "type": "fir",
        "description": "128-tap FIR filter optimization journey with rule effectiveness tracking",
        "target_device": "xc7z020clg484-1"  # 常見 Zynq-7000 設備型號範例
    },
    "iterations": [
        {
            "id": None,  # ✅ 將在導入時自動生成隨機 UUID
            "iteration_number": 1,
            "approach_description": "Baseline design with separate shift and MAC loops",
            "code_snapshot": """// ============================================================================
// FIR128_Optimization_Demo - Iteration #1: Baseline Design
// ============================================================================
// Previous: None (baseline)
// Target: Establish baseline performance
//
// Design Approach:
// - Separate shift and MAC loops (straightforward implementation)
// - Each loop individually pipelined with II=1
//
// Problem: Two sequential loops cause significant latency
// Expected: High II due to inter-loop dependencies
// ============================================================================

void fir(data_t *y, data_t x) {
    static data_t shift_reg[N];
    acc_t acc = 0;
    int i;

    Shift_Accum_Loop:
    for (i = N - 1; i > 0; i--) {
        // Basic pipeline: attempt II=1 for shift loop
        // Result: High II (264) due to sequential loop structure
        #pragma HLS PIPELINE II=1
        shift_reg[i] = shift_reg[i - 1];
    }
    shift_reg[0] = x;

    MAC:
    for (i = N - 1; i >= 0; i--) {
        // Basic pipeline: attempt II=1 for MAC loop
        // Result: Combined with shift loop → total II=264
        #pragma HLS PIPELINE II=1
        acc += shift_reg[i] * c[i];
    }
    *y = acc;
}""",
            "pragmas_used": ["#pragma HLS PIPELINE II=1"],
            "prompt_used": "Develop the FIR using Vitis HLS based on the files in the fir128 folder. Only one lane can be used for computation. Create a baseline folder inside fir128 for this project. Run csim, synthesis, and cosim.",
            "cursor_reasoning": "Starting with straightforward implementation to establish baseline",
            "synthesis_result": {
                "ii_achieved": 264,
                "ii_target": 1,
                "latency_cycles": None,
                "timing_met": None,
                "resource_usage": {"DSP": 1},
                "clock_period_ns": None
            },
            "rules_applied": []  # 基準版本，沒有應用特定優化規則
        },
        {
            "id": None,  # ✅ 將在導入時自動生成隨機 UUID
            "iteration_number": 2,
            "approach_description": "Merged shift and MAC into single loop using ternary operator",
            "code_snapshot": """// ============================================================================
// FIR128_Optimization_Demo - Iteration #2: Loop Merge
// ============================================================================
// Previous: Iteration #1 (II=264 cycles, two separate loops)
// Target: Reduce loop overhead by merging operations
//
// Problem Identified:
// - Two sequential loops (shift + MAC) cause high II
// - Loop-carried dependencies between loops
//
// Optimizations Applied:
// 1. Loop Merge:
//    - What: Combine shift and MAC into single loop
//    - Why: Eliminate inter-loop dependencies, reduce overhead
//    - How: Use ternary operator for conditional shift
//    - Expected: ~50% II reduction
//
// Applied Rule: P001 (Merge related operations into single loops)
// ============================================================================

void fir(data_t *y, data_t x) {
    static data_t shift_reg[N];
    acc_t acc = 0;
    int i;

    TDL_and_MAC:
    for (i = N - 1; i >= 0; i--) {
        // Pipeline: Single merged loop with II=1 target
        // Loop Merge: Combine shift and MAC operations
        // Rationale: Reduces overhead from 2 loops to 1
        // Result: II=134 (improved from 264, -49%)
        #pragma HLS PIPELINE II=1
        
        acc += shift_reg[i] * c[i];
        // Ternary operator: Conditionally select input (i==0) or shifted value
        // Enables single-cycle execution without separate shift loop
        shift_reg[i] = (i == 0) ? x : shift_reg[i - 1];
    }
    *y = acc;
}""",
            "pragmas_used": ["#pragma HLS PIPELINE II=1"],
            "prompt_used": "Merge related operations into single loops: Combine shifting, selection, and computation (e.g., using conditionals like ternaries) to reduce loop-carried dependencies and hazards.",
            "cursor_reasoning": "KB suggested pattern 'Merge related operations into single loops' - applying to reduce loop overhead",
            "synthesis_result": {
                "ii_achieved": 134,
                "ii_target": 1,
                "latency_cycles": None,
                "timing_met": None,
                "resource_usage": {"DSP": 1},
                "clock_period_ns": None
            },
            "rules_applied": [
                {
                    "rule_code": "P001",  # 使用用戶提示編號
                    "rule_keywords": ["merge", "related operations", "single loop"],
                    "rule_description": "Merge related operations into single loops by combining shifting, selection, and computation using conditionals",
                    "expected_benefit": "Reduce loop overhead and dependencies",
                    "previous_ii": 264,
                    "current_ii": 134,
                    "success": True
                }
            ]
        },
        {
            "id": None,  # ✅ 將在導入時自動生成隨機 UUID
            "iteration_number": 3,
            "approach_description": "Applied pipeline rewind optimization to merged loop",
            "code_snapshot": """// ============================================================================
// FIR128_Optimization_Demo - Iteration #3: Pipeline Rewind
// ============================================================================
// Previous: Iteration #2 (II=134 cycles, merged loop)
// Target: Further improve II by enabling overlapping execution
//
// Problem Identified:
// - II=134 still high (though improved from 264)
// - Finite-iteration loop not fully optimized
//
// Optimizations Applied:
// 1. Pipeline Rewind:
//    - What: Add 'rewind' option to PIPELINE pragma
//    - Why: Enable overlapping execution for finite loops without gaps
//    - Parameters: rewind (specifically for finite-iteration loops)
//    - Expected: Small II improvement (~5%)
//
// Applied Rule: P002 (Apply pipeline rewind to finite-iteration loops)
// ============================================================================

void fir(data_t *y, data_t x) {
    static data_t shift_reg[N];
    acc_t acc = 0;
    int i;

    TDL_and_MAC:
    for (i = N - 1; i >= 0; i--) {
        // Pipeline with Rewind: Overlapping execution without gaps
        // Parameters: II=1 target, rewind for finite loops
        // Rationale: Iteration #2 used basic pipeline, rewind improves efficiency
        // Result: II=128 (improved from 134, -4.5%)
        #pragma HLS PIPELINE II=1 rewind
        
        acc += shift_reg[i] * c[i];
        // Ternary operator: Same as Iteration #2, retained
        shift_reg[i] = (i == 0) ? x : shift_reg[i - 1];
    }
    *y = acc;
}""",
            "pragmas_used": ["#pragma HLS PIPELINE II=1 rewind"],
            "prompt_used": "try pipeline rewind",
            "cursor_reasoning": "Applied P002: pipeline rewind to enable overlapping execution of successive iterations without gaps",
            "synthesis_result": {
                "ii_achieved": 128,
                "ii_target": 1,
                "latency_cycles": None,
                "timing_met": None,
                "resource_usage": {"DSP": 1},
                "clock_period_ns": None
            },
            "rules_applied": [
                {
                    "rule_code": "P002",  # 使用用戶提示編號
                    "rule_keywords": ["pipeline", "rewind", "finite-iteration loops"],
                    "rule_description": "Apply #pragma HLS PIPELINE II=1 rewind to performance-critical loops, including finite-iteration loops",
                    "expected_benefit": "Enable overlapping execution without gaps",
                    "previous_ii": 134,
                    "current_ii": 128,
                    "success": True
                }
            ]
        }
        # 注意: 以上3个迭代没有user_reference_code（未提供，留空）
        # 如果有用户提供代码的迭代，格式如下：
        # {
        #     "id": "...",
        #     "iteration_number": 4,
        #     "approach_description": "Based on user's C code, optimized with array partition",
        #     "user_reference_code": """
        #         // 用户提供的C代码
        #         void fir_baseline(int *out, int in, int coef[128]) {
        #             static int buffer[128];
        #             for (int i = 127; i > 0; i--) buffer[i] = buffer[i-1];
        #             buffer[0] = in;
        #             int sum = 0;
        #             for (int i = 0; i < 128; i++) sum += buffer[i] * coef[i];
        #             *out = sum;
        #         }
        #     """,
        #     "user_specification": "Target: II=1, Data: 16-bit, Constraints: minimize DSP",
        #     "reference_metadata": {
        #         "language": "c",
        #         "code_type": "baseline_implementation",
        #         "source": "user_provided",
        #         "has_pseudocode": False
        #     },
        #     "code_snapshot": "/* 优化后的HLS实现 */",
        #     "pragmas_used": ["..."],
        #     "prompt_used": "优化用户提供的C代码",
        #     "cursor_reasoning": "User's code has 2 separate loops...",
        #     "synthesis_result": {...},
        #     "rules_applied": [...]
        # }
    ]
}

async def find_matching_rule(conn, rule_code=None, keywords=None, description=None):
    """
    在 hls_rules 表中查找匹配的規則
    
    简化为两级匹配（100%准确）
    
    匹配優先級（僅2級）:
    1. rule_code 精確匹配（P###/R###）     - 100% 準確
    2. 完整描述完全相同匹配                 - 100% 準確（逐字符）
    3. 如果都沒匹配 → 返回 None（不記錄不確定的）
    
    理念: 宁可不记录，也不要误记录（质量 > 数量）
    """
    
    # 方法 1: 使用規則編號（最優先，100% 避免混淆）⭐
    if rule_code:
        rule = await conn.fetchrow("""
            SELECT id, rule_code, rule_text, category, priority
            FROM hls_rules
            WHERE rule_code = $1
            LIMIT 1
        """, rule_code)
        
        if rule:
            return rule
    
    # 方法 2: 完整描述完全相同匹配（100% 準確）⭐
    if description:
        rule = await conn.fetchrow("""
            SELECT id, rule_code, rule_text, category, priority
            FROM hls_rules
            WHERE LOWER(rule_text) = LOWER($1)
            LIMIT 1
        """, description)
        
        if rule:
            return rule
    
    # ⚠️ 不再使用模糊匹配（关键字/LIKE）
    # 原因: 误匹配风险高（30-50%），污染知识库统计数据
    # 策略: 宁可不记录，也不要误记录
    
    return None  # 未找到100%准确的匹配，不记录

async def record_rule_effectiveness(conn, rule_id, project_type, success, ii_improvement):
    """
    記錄規則應用效果到 rules_effectiveness 表
    
    UPSERT 模式（覆蓋，不累加）：
    - 適用於 import_fir128_data.py（數據修正/初始化）
    - 重複運行會覆蓋統計值，不會累加
    - 與 API 自動記錄（累加模式）不同
    
    返回: (effectiveness_id, is_new)
    """
    # 檢查是否已有記錄
    existing = await conn.fetchrow("""
        SELECT id
        FROM rules_effectiveness
        WHERE rule_id = $1 AND project_type = $2
    """, rule_id, project_type)
    
    if existing:
        # 覆蓋模式：直接更新統計值（不累加）⭐
        await conn.execute("""
            UPDATE rules_effectiveness
            SET times_applied = $1,
                success_count = $2,
                avg_ii_improvement = $3,
                last_applied_at = CURRENT_TIMESTAMP
            WHERE id = $4
        """, 1,  # times_applied = 1（覆蓋，不累加）
            1 if success else 0,  # success_count（覆蓋）
            ii_improvement if success else 0,  # avg（覆蓋）
            existing['id'])
        
        return existing['id'], False  # False = 更新
    else:
        # 創建新記錄
        effectiveness_id = uuid4()
        await conn.execute("""
            INSERT INTO rules_effectiveness (
                id, rule_id, project_type, times_applied, success_count,
                avg_ii_improvement, last_applied_at
            ) VALUES ($1, $2, $3, $4, $5, $6, CURRENT_TIMESTAMP)
        """, effectiveness_id, rule_id, project_type, 1,
            1 if success else 0,
            ii_improvement if success else 0)
        
        return effectiveness_id, True  # True = 新建

async def import_fir128_with_effectiveness():
    """導入 FIR128 數據並記錄規則效果"""
    print("=" * 70)
    print("FIR128 數據導入工具（包含規則效果記錄）")
    print("=" * 70)
    print()
    
    conn = await asyncpg.connect(DATABASE_URL)
    
    try:
        # 1. 創建專案（UPSERT：覆蓋模式）
        print("[1/5] 創建 FIR128 專案...")
        project = FIR128_DATA["project"]
        project_id = UUID(project["id"])
        
        existing = await conn.fetchval(
            "SELECT id FROM projects WHERE id = $1", project_id
        )
        
        if not existing:
            await conn.execute("""
                INSERT INTO projects (id, name, type, description, target_device)
                VALUES ($1, $2, $3, $4, $5)
            """, project_id, project["name"], project["type"],
                project["description"], project["target_device"])
            print(f"  ✓ 專案已創建: {project_id}")
        else:
            # 覆蓋模式：更新專案信息
            await conn.execute("""
                UPDATE projects 
                SET name = $1, type = $2, description = $3, target_device = $4
                WHERE id = $5
            """, project["name"], project["type"], project["description"], 
                project["target_device"], project_id)
            print(f"  ✓ 專案已存在，已更新: {project_id}")
        
        print()
        
        # 2. 插入設計迭代（UPSERT：覆蓋模式，改用 project_id + iteration_number 查詢）
        print("[2/5] 插入設計迭代...")
        base_time = datetime.now() - timedelta(days=7)
        
        # 保存生成的 iter_id 供後續步驟使用
        iteration_ids = {}
        
        for i, iteration in enumerate(FIR128_DATA["iterations"]):
            # 先用 (project_id, iteration_number) 查詢是否已存在
            existing = await conn.fetchval("""
                SELECT id FROM design_iterations 
                WHERE project_id = $1 AND iteration_number = $2
            """, project_id, iteration["iteration_number"])
            
            if existing:
                # 已存在，使用現有 UUID
                iter_id = existing
                print(f"  → 找到現有 UUID: {iter_id}")
            else:
                # 不存在，生成新 UUID
                if iteration["id"] is None:
                    iter_id = uuid4()
                    print(f"  → 生成隨機 UUID: {iter_id}")
                else:
                    iter_id = UUID(iteration["id"])
                    print(f"  → 使用指定 UUID: {iter_id}")
            
            # 保存 iter_id 供後續使用
            iteration_ids[iteration["iteration_number"]] = iter_id
            
            # 获取用户输入字段（如果存在）
            user_ref_code = iteration.get("user_reference_code")
            user_spec = iteration.get("user_specification")
            ref_metadata = iteration.get("reference_metadata")
            
            # 計算 code_snapshot 的 SHA256 hash (用於去重和版本追蹤)
            code_hash = hashlib.sha256(iteration["code_snapshot"].encode('utf-8')).hexdigest()
            
            # UPSERT 模式：改用 (project_id, iteration_number) 查詢後，覆蓋或新增
            if existing:
                # 已存在，UPDATE（覆蓋）
                await conn.execute("""
                    UPDATE design_iterations
                    SET approach_description = $1,
                        code_snapshot = $2,
                        code_hash = $3,
                        pragmas_used = $4,
                        prompt_used = $5,
                        cursor_reasoning = $6,
                        user_reference_code = $7,
                        user_specification = $8,
                        reference_metadata = $9
                    WHERE id = $10
                """, iteration["approach_description"], iteration["code_snapshot"], code_hash,
                    iteration["pragmas_used"], iteration["prompt_used"],
                    iteration["cursor_reasoning"],
                    user_ref_code, user_spec,
                    json.dumps(ref_metadata) if ref_metadata else None,
                    iter_id)
                
                print(f"  ✓ 迭代 {i+1}: 更新 - {iteration['approach_description'][:50]}... (hash: {code_hash[:16]}...)")
            else:
                # 不存在，INSERT（新增）
                await conn.execute("""
                    INSERT INTO design_iterations (
                        id, project_id, iteration_number, approach_description,
                        code_snapshot, code_hash, pragmas_used, prompt_used, cursor_reasoning,
                        user_reference_code, user_specification, reference_metadata,
                        created_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                """, iter_id, project_id, iteration["iteration_number"],
                    iteration["approach_description"], iteration["code_snapshot"], code_hash,
                    iteration["pragmas_used"], iteration["prompt_used"],
                    iteration["cursor_reasoning"],
                    user_ref_code, user_spec,
                    json.dumps(ref_metadata) if ref_metadata else None,
                    base_time + timedelta(days=i*2))
                
                print(f"  ✓ 迭代 {i+1}: 新建 - {iteration['approach_description'][:50]}... (hash: {code_hash[:16]}...)")
        
        print()
        
        # 3. 插入綜合結果
        print("[3/5] 插入綜合結果...")
        for iteration in FIR128_DATA["iterations"]:
            # 使用之前保存的 iter_id
            iter_id = iteration_ids[iteration["iteration_number"]]
            result = iteration["synthesis_result"]
            
            existing_result_id = await conn.fetchval(
                "SELECT id FROM synthesis_results WHERE iteration_id = $1", iter_id
            )
            
            if not existing_result_id:
                # 插入新記錄
                await conn.execute("""
                    INSERT INTO synthesis_results (
                        id, iteration_id, ii_achieved, ii_target, latency_cycles,
                        timing_met, resource_usage, clock_period_ns
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """, uuid4(), iter_id, result["ii_achieved"], result["ii_target"],
                    result["latency_cycles"], result["timing_met"],
                    json.dumps(result["resource_usage"]), result["clock_period_ns"])
                
                print(f"  ✓ 迭代 {iteration['iteration_number']}: 新建 - " +
                      f"II={result['ii_achieved']}, Latency={result['latency_cycles']}")
            else:
                # 更新已存在的記錄（UPSERT 模式）⭐ 新增
                await conn.execute("""
                    UPDATE synthesis_results
                    SET ii_achieved = $1,
                        ii_target = $2,
                        latency_cycles = $3,
                        timing_met = $4,
                        resource_usage = $5,
                        clock_period_ns = $6
                    WHERE id = $7
                """, result["ii_achieved"], result["ii_target"],
                    result["latency_cycles"], result["timing_met"],
                    json.dumps(result["resource_usage"]), result["clock_period_ns"],
                    existing_result_id)
                
                print(f"  ✓ 迭代 {iteration['iteration_number']}: 更新 - " +
                      f"II={result['ii_achieved']}, Latency={result['latency_cycles']}")
        
        print()
        
        # 4. 記錄規則應用效果 ⭐ 新增功能
        print("[4/5] 記錄規則應用效果...")
        rules_recorded = 0
        
        for iteration in FIR128_DATA["iterations"]:
            if not iteration.get("rules_applied"):
                continue
            
            for rule_app in iteration["rules_applied"]:
                # 查找匹配的規則（優先使用 rule_code）
                rule = await find_matching_rule(
                    conn,
                    rule_code=rule_app.get("rule_code"),
                    keywords=rule_app.get("rule_keywords"),
                    description=rule_app.get("rule_description")
                )
                
                if rule:
                    # 計算 II 改善
                    ii_improvement = rule_app["previous_ii"] - rule_app["current_ii"]
                    success = rule_app["success"] and ii_improvement > 0
                    
                    # 記錄效果
                    eff_id, is_new = await record_rule_effectiveness(
                        conn,
                        rule["id"],
                        "fir",
                        success,
                        ii_improvement if success else 0
                    )
                    
                    action = "新建" if is_new else "更新"
                    status = "✓" if success else "✗"
                    print(f"  {status} {action} 規則效果:")
                    print(f"     規則: {rule['rule_text'][:60]}")
                    print(f"     類別: {rule['category']} | 優先級: {rule['priority']}")
                    print(f"     成功: {'是' if success else '否'} | " +
                          f"II 改善: {ii_improvement} cycles")
                    rules_recorded += 1
                else:
                    print(f"  ⚠️  未找到匹配規則: {rule_app['rule_description'][:50]}...")
        
        print(f"\n  ✓ 共記錄 {rules_recorded} 條規則效果")
        print()
        
        # 5. 驗證導入結果
        print("[5/5] 驗證導入結果...")
        print()
        
        # 檢查迭代進度
        iterations = await conn.fetch("""
            SELECT di.iteration_number, sr.ii_achieved, sr.latency_cycles
            FROM design_iterations di
            JOIN synthesis_results sr ON di.id = sr.iteration_id
            WHERE di.project_id = $1
            ORDER BY di.iteration_number
        """, project_id)
        
        print("  迭代進度:")
        for i, iter in enumerate(iterations):
            print(f"    迭代 {iter['iteration_number']}: " +
                  f"II={iter['ii_achieved']}, Latency={iter['latency_cycles']}")
            
            if i > 0:
                prev_ii = iterations[i-1]['ii_achieved']
                improvement = prev_ii - iter['ii_achieved']
                percentage = (improvement / prev_ii) * 100
                print(f"             改進: -{improvement} cycles ({percentage:.1f}%)")
        
        print()
        
        # 檢查規則效果統計
        effectiveness = await conn.fetch("""
            SELECT r.rule_text, r.category, re.times_applied, 
                   re.success_count, re.avg_ii_improvement
            FROM rules_effectiveness re
            JOIN hls_rules r ON re.rule_id = r.id
            WHERE re.project_type = 'fir'
            ORDER BY re.avg_ii_improvement DESC
        """)
        
        if effectiveness:
            print("  規則效果統計:")
            for eff in effectiveness:
                success_rate = (eff['success_count'] / eff['times_applied'] * 100) 
                print(f"    • {eff['rule_text'][:50]}")
                print(f"      應用: {eff['times_applied']} 次 | " +
                      f"成功率: {success_rate:.0f}% | " +
                      f"平均改善: {eff['avg_ii_improvement']:.1f} cycles")
        
        print()
        print("=" * 70)
        print("✓ FIR128 數據及規則效果導入完成!")
        print("=" * 70)
        
    except Exception as e:
        print(f"\n✗ 錯誤: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await conn.close()

async def main():
    """主函數"""
    print("\n準備導入 FIR128 數據（包含規則效果記錄）...")
    print("這將記錄規則應用的成功率和 II 改善效果。\n")
    
    await import_fir128_with_effectiveness()
    
    print("\n下一步:")
    print("  1. 查看規則效果:")
    print('     curl "http://localhost:8000/api/rules/effective?project_type=fir"')
    print("  2. 查看成功率排名:")
    print('     psql -d hls_knowledge -c "SELECT * FROM rule_effectiveness_summary WHERE times_applied > 0 LIMIT 10"')

if __name__ == "__main__":
    asyncio.run(main())

