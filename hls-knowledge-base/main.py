"""
HLS Knowledge Base - FastAPI Server
提供 RESTful API 供 Cursor 查詢和記錄 HLS 設計
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID, uuid4
import asyncpg
import os
import json
import hashlib  # 用於計算 code_snapshot 的 SHA256 hash

# ==================== Configuration ====================
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://hls_user:hls_pass_2024@localhost:5432/hls_knowledge"
)

app = FastAPI(
    title="HLS Knowledge Base API",
    description="Knowledge base for HLS design patterns and optimization",
    version="1.0.0"
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== Database Connection ====================
async def get_db_pool():
    """獲取數據庫連接池"""
    return await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)

@app.on_event("startup")
async def startup():
    app.state.pool = await get_db_pool()
    print(f"✓ Database pool created: {DATABASE_URL}")

@app.on_event("shutdown")
async def shutdown():
    await app.state.pool.close()
    print("✓ Database pool closed")

# ==================== Pydantic Models ====================
class ProjectCreate(BaseModel):
    name: str
    type: str = Field(..., description="Project type: fir, matmul, conv, etc.")
    description: Optional[str] = None
    target_device: Optional[str] = "xc7z020clg484-1"

class DesignIterationCreate(BaseModel):
    project_id: UUID
    approach_description: str
    code_snapshot: str
    pragmas_used: List[str]
    prompt_used: Optional[str] = None
    cursor_reasoning: Optional[str] = None
    user_reference_code: Optional[str] = Field(None, description="用户提供的参考代码（C/C++/pseudocode）。如未提供则为None")
    user_specification: Optional[str] = Field(None, description="用户的需求规格和约束。如未提供则为None")
    reference_metadata: Optional[Dict[str, Any]] = Field(None, description="参考信息元数据JSON。如未提供则为None")

class SynthesisResultCreate(BaseModel):
    iteration_id: UUID
    ii_achieved: int
    ii_target: int
    latency_cycles: int
    timing_met: bool
    resource_usage: Dict[str, int]
    clock_period_ns: Optional[float] = 10.0

class SynthesisResultData(BaseModel):
    """综合结果数据（不包含iteration_id，用于complete_iteration）"""
    ii_achieved: int
    ii_target: int
    latency_cycles: int
    timing_met: bool
    resource_usage: Dict[str, int]
    clock_period_ns: Optional[float] = 10.0

class RuleEffectivenessUpdate(BaseModel):
    rule_code: Optional[str] = None  # 優先使用規則編號
    rule_text: Optional[str] = None  # 備用方案：使用規則文本
    project_type: str
    was_successful: bool
    ii_improvement: Optional[float] = None

class RuleApplication(BaseModel):
    rule_code: Optional[str] = None  # 優先使用規則編號
    rule_keywords: Optional[List[str]] = None  # 備用方案
    rule_description: Optional[str] = None  # 備用方案
    previous_ii: int
    current_ii: int
    success: bool
    category: Optional[str] = None

class CompleteIterationCreate(BaseModel):
    project_id: UUID
    project_name: Optional[str] = None
    project_type: str = Field(..., description="Project type: fir, matmul, conv, etc.")
    iteration: DesignIterationCreate
    synthesis_result: SynthesisResultData  # 使用不包含iteration_id的版本
    rules_applied: List[RuleApplication] = []

# ==================== API Endpoints ====================

@app.get("/health")
async def health_check():
    """健康檢查端點"""
    try:
        async with app.state.pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return {
            "status": "healthy",
            "database": "connected",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }

# ---------- Projects ----------
@app.post("/api/projects")
async def create_project(project: ProjectCreate):
    """創建新專案"""
    async with app.state.pool.acquire() as conn:
        project_id = uuid4()
        await conn.execute("""
            INSERT INTO projects (id, name, type, description, target_device)
            VALUES ($1, $2, $3, $4, $5)
        """, project_id, project.name, project.type, project.description, project.target_device)
        
        return {
            "project_id": str(project_id),
            "name": project.name,
            "type": project.type
        }

@app.get("/api/projects/{project_id}")
async def get_project(project_id: UUID):
    """獲取專案詳情"""
    async with app.state.pool.acquire() as conn:
        project = await conn.fetchrow("""
            SELECT * FROM projects WHERE id = $1
        """, project_id)
        
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        
        return dict(project)

# ---------- Design Iterations ----------
@app.post("/api/design/start")
async def start_design_iteration(iteration: DesignIterationCreate):
    """開始新的設計迭代"""
    async with app.state.pool.acquire() as conn:
        # 獲取當前專案的迭代數
        iteration_num = await conn.fetchval("""
            SELECT COALESCE(MAX(iteration_number), 0) + 1
            FROM design_iterations
            WHERE project_id = $1
        """, iteration.project_id)
        
        iteration_id = uuid4()
        
        # 計算 code_snapshot 的 SHA256 hash (用於去重和版本追蹤)
        code_hash = hashlib.sha256(iteration.code_snapshot.encode('utf-8')).hexdigest()
        
        await conn.execute("""
            INSERT INTO design_iterations (
                id, project_id, iteration_number, approach_description,
                code_snapshot, code_hash, pragmas_used, prompt_used, cursor_reasoning,
                user_reference_code, user_specification, reference_metadata
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
        """, iteration_id, iteration.project_id, iteration_num,
            iteration.approach_description, iteration.code_snapshot, code_hash,
            iteration.pragmas_used, iteration.prompt_used, iteration.cursor_reasoning,
            iteration.user_reference_code, iteration.user_specification,
            json.dumps(iteration.reference_metadata) if iteration.reference_metadata else None)
        
        return {
            "iteration_id": str(iteration_id),
            "iteration_number": iteration_num,
            "project_id": str(iteration.project_id)
        }

@app.post("/api/design/{iteration_id}/synthesis_result")
async def record_synthesis_result(iteration_id: UUID, result: SynthesisResultCreate):
    """記錄 HLS 合成結果"""
    async with app.state.pool.acquire() as conn:
        result_id = uuid4()
        await conn.execute("""
            INSERT INTO synthesis_results (
                id, iteration_id, ii_achieved, ii_target, latency_cycles,
                timing_met, resource_usage, clock_period_ns
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        """, result_id, iteration_id, result.ii_achieved, result.ii_target,
            result.latency_cycles, result.timing_met,
            json.dumps(result.resource_usage), result.clock_period_ns)
        
        return {
            "result_id": str(result_id),
            "iteration_id": str(iteration_id),
            "ii_achieved": result.ii_achieved
        }

# ---------- Knowledge Base Queries ----------
@app.get("/api/design/similar")
async def find_similar_designs(
    project_type: str = Query(..., description="Project type: fir, matmul, conv"),
    target_ii: Optional[int] = Query(None, description="Target II value"),
    limit: int = Query(5, ge=1, le=20, description="Number of results")
):
    """查詢相似的成功設計案例"""
    async with app.state.pool.acquire() as conn:
        query = """
            SELECT 
                di.id as iteration_id,
                di.project_id as project_id,
                p.name as project_name,
                p.type as project_type,
                di.iteration_number,
                di.approach_description,
                di.code_hash,
                di.pragmas_used,
                di.user_reference_code,
                di.user_specification,
                di.reference_metadata,
                sr.ii_achieved,
                sr.ii_target,
                sr.latency_cycles,
                sr.resource_usage,
                di.created_at
            FROM design_iterations di
            JOIN projects p ON di.project_id = p.id
            JOIN synthesis_results sr ON di.id = sr.iteration_id
            WHERE p.type = $1
            AND sr.ii_achieved IS NOT NULL
        """
        
        params = [project_type]
        
        if target_ii is not None:
            query += " AND sr.ii_achieved <= $2"
            params.append(target_ii)
            query += " ORDER BY sr.ii_achieved ASC"
        else:
            query += " ORDER BY sr.ii_achieved ASC"
        
        query += f" LIMIT ${len(params) + 1}"
        params.append(limit)
        
        results = await conn.fetch(query, *params)
        
        return {
            "query": {
                "project_type": project_type,
                "target_ii": target_ii,
                "limit": limit
            },
            "results": [dict(r) for r in results]
        }

@app.get("/api/design/{iteration_id}/code")
async def get_iteration_code(iteration_id: UUID):
    """獲取特定迭代的完整程式碼（code_snapshot）
    
    用途：當需要查看或參考完整程式碼時使用
    注意：code_snapshot 可能很大（數 KB），建議只在必要時查詢
    """
    async with app.state.pool.acquire() as conn:
        result = await conn.fetchrow("""
            SELECT 
                di.id,
                di.iteration_number,
                di.approach_description,
                di.code_snapshot,
                di.code_hash,
                p.name as project_name
            FROM design_iterations di
            JOIN projects p ON di.project_id = p.id
            WHERE di.id = $1
        """, iteration_id)
        
        if not result:
            raise HTTPException(status_code=404, detail="Iteration not found")
        
        return {
            "iteration_id": str(result['id']),
            "iteration_number": result['iteration_number'],
            "project_name": result['project_name'],
            "approach_description": result['approach_description'],
            "code_snapshot": result['code_snapshot'],
            "code_hash": result['code_hash']
        }

@app.get("/api/rules/effective")
async def get_effective_rules(
    project_type: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    rule_type: Optional[str] = Query(None),  # 'official' or 'user_prompt'
    min_success_rate: float = Query(0.7, ge=0.0, le=1.0)
):
    """獲取有效的 HLS 規則（支持 rule_type 過濾）"""
    async with app.state.pool.acquire() as conn:
        # 使用子查詢方式避免 GROUP BY 問題
        query = """
            SELECT * FROM (
                SELECT 
                    r.id,
                    r.rule_code,
                    r.rule_type,
                    r.rule_text,
                    r.category,
                    r.priority,
                    r.source,
                    COALESCE(re.times_applied, 0) as times_applied,
                    COALESCE(re.success_count, 0) as success_count,
                    CASE 
                        WHEN COALESCE(re.times_applied, 0) > 0 
                        THEN CAST(COALESCE(re.success_count, 0) AS FLOAT) / re.times_applied
                        ELSE 0
                    END as success_rate,
                    re.avg_ii_improvement
                FROM hls_rules r
                LEFT JOIN rules_effectiveness re ON r.id = re.rule_id
        """
        
        conditions = []
        params = []
        
        if project_type:
            params.append(project_type)
            conditions.append(f"(re.project_type = ${len(params)} OR re.project_type IS NULL)")
        
        if category:
            params.append(category)
            conditions.append(f"r.category = ${len(params)}")
        
        if rule_type:
            params.append(rule_type)
            conditions.append(f"r.rule_type = ${len(params)}")
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        # 子查詢結束，添加過濾條件
        query += """
            ) AS filtered_rules
            WHERE success_rate >= $""" + str(len(params) + 1) + """
            ORDER BY success_rate DESC, priority DESC
        """
        params.append(min_success_rate)
        
        results = await conn.fetch(query, *params)
        
        return {
            "filters": {
                "project_type": project_type,
                "category": category,
                "rule_type": rule_type,
                "min_success_rate": min_success_rate
            },
            "rules": [dict(r) for r in results]
        }

@app.post("/api/rules/update_effectiveness")
async def update_rule_effectiveness(update: RuleEffectivenessUpdate):
    """更新規則的有效性統計（支持 rule_code 或 rule_text）"""
    async with app.state.pool.acquire() as conn:
        # 查找 rule_id（優先使用 rule_code）
        rule_id = None
        
        if update.rule_code:
            rule_id = await conn.fetchval("""
                SELECT id FROM hls_rules WHERE rule_code = $1
            """, update.rule_code)
        
        if not rule_id and update.rule_text:
            rule_id = await conn.fetchval("""
                SELECT id FROM hls_rules WHERE rule_text = $1
            """, update.rule_text)
        
        if not rule_id:
            raise HTTPException(status_code=404, detail="Rule not found")
        
        # 更新或插入 effectiveness 記錄
        await conn.execute("""
            INSERT INTO rules_effectiveness (
                rule_id, project_type, times_applied, success_count, avg_ii_improvement
            ) VALUES ($1, $2, 1, $3, $4)
            ON CONFLICT (rule_id, project_type) DO UPDATE SET
                times_applied = rules_effectiveness.times_applied + 1,
                success_count = rules_effectiveness.success_count + $3,
                avg_ii_improvement = 
                    CASE 
                        WHEN $4 IS NOT NULL THEN
                            (COALESCE(rules_effectiveness.avg_ii_improvement, 0) * rules_effectiveness.times_applied + $4) 
                            / (rules_effectiveness.times_applied + 1)
                        ELSE rules_effectiveness.avg_ii_improvement
                    END
        """, rule_id, update.project_type, 
            1 if update.was_successful else 0, 
            update.ii_improvement)
        
        return {
            "status": "updated",
            "rule_id": str(rule_id),
            "was_successful": update.was_successful
        }

# ---------- Complete Iteration (一次性接口) ----------
@app.post("/api/design/complete_iteration")
async def record_complete_iteration(data: CompleteIterationCreate):
    """
    完整记录一次设计迭代（推荐使用）
    一次API调用完成：创建项目、记录迭代、记录综合结果、更新规则效果
    """
    async with app.state.pool.acquire() as conn:
        async with conn.transaction():
            # 1. 确保项目存在
            project_exists = await conn.fetchval(
                "SELECT id FROM projects WHERE id = $1", data.project_id
            )
            
            if not project_exists:
                # 自动创建项目
                project_name = data.project_name or f"{data.project_type.upper()}_Design"
                await conn.execute("""
                    INSERT INTO projects (id, name, type, description)
                    VALUES ($1, $2, $3, $4)
                """, data.project_id, project_name, data.project_type,
                    f"Auto-created project for {data.project_type} design")
            
            # 2. 获取迭代序号
            iteration_num = await conn.fetchval("""
                SELECT COALESCE(MAX(iteration_number), 0) + 1
                FROM design_iterations
                WHERE project_id = $1
            """, data.project_id)
            
            # 3. 插入迭代记录
            iteration_id = uuid4()
            
            # 計算 code_snapshot 的 SHA256 hash (用於去重和版本追蹤)
            code_hash = hashlib.sha256(data.iteration.code_snapshot.encode('utf-8')).hexdigest()
            
            await conn.execute("""
                INSERT INTO design_iterations (
                    id, project_id, iteration_number, approach_description,
                    code_snapshot, code_hash, pragmas_used, prompt_used, cursor_reasoning,
                    user_reference_code, user_specification, reference_metadata
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            """, iteration_id, data.project_id, iteration_num,
                data.iteration.approach_description, data.iteration.code_snapshot, code_hash,
                data.iteration.pragmas_used, data.iteration.prompt_used,
                data.iteration.cursor_reasoning,
                data.iteration.user_reference_code, data.iteration.user_specification,
                json.dumps(data.iteration.reference_metadata) if data.iteration.reference_metadata else None)
            
            # 4. 插入综合结果
            result_id = uuid4()
            await conn.execute("""
                INSERT INTO synthesis_results (
                    id, iteration_id, ii_achieved, ii_target, latency_cycles,
                    timing_met, resource_usage, clock_period_ns
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """, result_id, iteration_id, data.synthesis_result.ii_achieved,
                data.synthesis_result.ii_target, data.synthesis_result.latency_cycles,
                data.synthesis_result.timing_met,
                json.dumps(data.synthesis_result.resource_usage),
                data.synthesis_result.clock_period_ns)
            
            # 5. 记录规则应用效果
            rules_recorded = 0
            for rule_app in data.rules_applied:
                # 查找匹配的规则
                rule = None
                for keyword in rule_app.rule_keywords:
                    rule = await conn.fetchrow("""
                        SELECT id, rule_text, category, priority
                        FROM hls_rules
                        WHERE LOWER(rule_text) LIKE $1
                        ORDER BY priority DESC
                        LIMIT 1
                    """, f"%{keyword.lower()}%")
                    if rule:
                        break
                
                if rule:
                    # 计算II改善
                    ii_improvement = rule_app.previous_ii - rule_app.current_ii
                    success = rule_app.success and ii_improvement > 0
                    
                    # 更新规则效果统计
                    existing = await conn.fetchrow("""
                        SELECT id, times_applied, success_count, avg_ii_improvement
                        FROM rules_effectiveness
                        WHERE rule_id = $1 AND project_type = $2
                    """, rule['id'], data.project_type)
                    
                    if existing:
                        # 更新现有记录
                        new_times = existing['times_applied'] + 1
                        new_success = existing['success_count'] + (1 if success else 0)
                        old_avg = float(existing['avg_ii_improvement'] or 0)
                        old_total = old_avg * existing['success_count']
                        new_total = old_total + (ii_improvement if success else 0)
                        new_avg = new_total / new_success if new_success > 0 else 0
                        
                        await conn.execute("""
                            UPDATE rules_effectiveness
                            SET times_applied = $1, success_count = $2,
                                avg_ii_improvement = $3, last_applied_at = CURRENT_TIMESTAMP
                            WHERE id = $4
                        """, new_times, new_success, new_avg, existing['id'])
                    else:
                        # 创建新记录
                        await conn.execute("""
                            INSERT INTO rules_effectiveness (
                                id, rule_id, project_type, times_applied, success_count,
                                avg_ii_improvement, last_applied_at
                            ) VALUES ($1, $2, $3, $4, $5, $6, CURRENT_TIMESTAMP)
                        """, uuid4(), rule['id'], data.project_type, 1,
                            1 if success else 0, ii_improvement if success else 0)
                    
                    rules_recorded += 1
            
            return {
                "status": "success",
                "iteration_id": str(iteration_id),
                "iteration_number": iteration_num,
                "project_id": str(data.project_id),
                "rules_recorded": rules_recorded,
                "message": f"完整迭代记录已创建（迭代#{iteration_num}，{rules_recorded}条规则效果已更新）"
            }

# ---------- Analytics ----------
@app.get("/api/analytics/project/{project_id}/progress")
async def get_project_progress(project_id: UUID):
    """獲取專案的優化進度"""
    async with app.state.pool.acquire() as conn:
        iterations = await conn.fetch("""
            SELECT 
                di.iteration_number,
                di.approach_description,
                sr.ii_achieved,
                sr.latency_cycles,
                sr.resource_usage,
                di.created_at
            FROM design_iterations di
            LEFT JOIN synthesis_results sr ON di.id = sr.iteration_id
            WHERE di.project_id = $1
            ORDER BY di.iteration_number ASC
        """, project_id)
        
        if not iterations:
            raise HTTPException(status_code=404, detail="No iterations found")
        
        # 計算改進
        progress = []
        for i, iter in enumerate(iterations):
            item = dict(iter)
            if i > 0 and iter['ii_achieved'] and iterations[i-1]['ii_achieved']:
                item['ii_improvement'] = iterations[i-1]['ii_achieved'] - iter['ii_achieved']
            progress.append(item)
        
        return {
            "project_id": str(project_id),
            "total_iterations": len(iterations),
            "iterations": progress
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
