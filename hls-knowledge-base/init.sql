-- HLS Knowledge Base - Database Schema (Clean Version)
-- PostgreSQL 15+
-- 只保留核心表結構，無示例數據

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ==================== Core Tables ====================

-- 1. Projects Table
CREATE TABLE IF NOT EXISTS projects (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    type VARCHAR(50) NOT NULL, -- fir, matmul, conv, etc.
    description TEXT,
    target_device VARCHAR(100) DEFAULT 'xc7z020clg484-1',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_projects_type ON projects(type);
CREATE INDEX IF NOT EXISTS idx_projects_created_at ON projects(created_at);

-- 2. HLS Rules Table (Dual-tier: Official Rules + User Prompts)
CREATE TABLE IF NOT EXISTS hls_rules (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    rule_code VARCHAR(10) UNIQUE, -- Unique identifier: R### (official) or P### (user prompt)
    rule_type VARCHAR(20) DEFAULT 'official', -- 'official' or 'user_prompt'
    rule_text TEXT NOT NULL UNIQUE,
    category VARCHAR(50) NOT NULL, -- pipeline, dataflow, memory, etc.
    priority INTEGER DEFAULT 5, -- 1-10, higher is more important
    description TEXT,
    source VARCHAR(100), -- e.g., 'UG1399', 'FIR128 project'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_rules_code ON hls_rules(rule_code);
CREATE INDEX IF NOT EXISTS idx_rules_type ON hls_rules(rule_type);
CREATE INDEX IF NOT EXISTS idx_rules_category ON hls_rules(category);
CREATE INDEX IF NOT EXISTS idx_rules_priority ON hls_rules(priority DESC);

-- 3. Design Iterations Table
CREATE TABLE IF NOT EXISTS design_iterations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    iteration_number INTEGER NOT NULL,
    approach_description TEXT NOT NULL,
    code_snapshot TEXT NOT NULL,
    code_hash VARCHAR(64), -- SHA256 hash for deduplication
    pragmas_used TEXT[], -- Array of pragma strings
    prompt_used TEXT, -- Cursor prompt that generated this
    cursor_reasoning TEXT, -- Cursor's reasoning for this approach
    user_reference_code TEXT, -- 用户提供的参考代码（C/C++/pseudocode/示例代码）
    user_specification TEXT, -- 用户的需求规格和约束条件
    reference_metadata JSONB, -- 参考信息的元数据 {"language": "c", "code_type": "baseline", "source": "user"}
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(project_id, iteration_number)
);

CREATE INDEX IF NOT EXISTS idx_iterations_project ON design_iterations(project_id);
CREATE INDEX IF NOT EXISTS idx_iterations_code_hash ON design_iterations(code_hash);
CREATE INDEX IF NOT EXISTS idx_iterations_created_at ON design_iterations(created_at);

-- 4. Synthesis Results Table
CREATE TABLE IF NOT EXISTS synthesis_results (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    iteration_id UUID NOT NULL REFERENCES design_iterations(id) ON DELETE CASCADE,
    ii_achieved INTEGER,
    ii_target INTEGER,
    latency_cycles INTEGER,
    timing_met BOOLEAN DEFAULT true,
    clock_period_ns DECIMAL(10, 3) DEFAULT 10.0,
    resource_usage JSONB, -- {DSP: 10, LUT: 1000, FF: 500, BRAM: 2}
    synthesis_time_seconds DECIMAL(10, 2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(iteration_id)
);

CREATE INDEX IF NOT EXISTS idx_results_iteration ON synthesis_results(iteration_id);
CREATE INDEX IF NOT EXISTS idx_results_ii_achieved ON synthesis_results(ii_achieved);
CREATE INDEX IF NOT EXISTS idx_results_resource_usage ON synthesis_results USING GIN(resource_usage);

-- 5. Rules Effectiveness Tracking
CREATE TABLE IF NOT EXISTS rules_effectiveness (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    rule_id UUID NOT NULL REFERENCES hls_rules(id) ON DELETE CASCADE,
    project_type VARCHAR(50) NOT NULL,
    times_applied INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0, -- II improved or timing met
    avg_ii_improvement DECIMAL(10, 2),
    last_applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(rule_id, project_type)
);

CREATE INDEX IF NOT EXISTS idx_effectiveness_rule ON rules_effectiveness(rule_id);
CREATE INDEX IF NOT EXISTS idx_effectiveness_type ON rules_effectiveness(project_type);
CREATE INDEX IF NOT EXISTS idx_effectiveness_success_rate ON rules_effectiveness((success_count::float / NULLIF(times_applied, 0)));

-- 6. Design Patterns Table
CREATE TABLE IF NOT EXISTS design_patterns (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL UNIQUE,
    description TEXT,
    code_template TEXT,
    typical_pragmas TEXT[],
    expected_ii_range INT4RANGE, -- e.g., [1, 10]
    project_types VARCHAR(50)[], -- Applicable project types
    success_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_patterns_name ON design_patterns(name);
CREATE INDEX IF NOT EXISTS idx_patterns_types ON design_patterns USING GIN(project_types);

-- ==================== Helper Functions ====================

-- Function to calculate II improvement percentage
CREATE OR REPLACE FUNCTION calculate_ii_improvement(
    old_ii INTEGER,
    new_ii INTEGER
) RETURNS DECIMAL AS $$
BEGIN
    IF old_ii IS NULL OR new_ii IS NULL OR old_ii = 0 THEN
        RETURN NULL;
    END IF;
    RETURN ((old_ii - new_ii)::DECIMAL / old_ii) * 100;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_projects_updated_at ON projects;
CREATE TRIGGER update_projects_updated_at
    BEFORE UPDATE ON projects
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ==================== Views for Common Queries ====================

-- View: Best designs per project type
CREATE OR REPLACE VIEW best_designs_by_type AS
SELECT DISTINCT ON (p.type)
    p.type as project_type,
    p.name as project_name,
    di.approach_description,
    sr.ii_achieved,
    sr.latency_cycles,
    sr.resource_usage,
    di.pragmas_used,
    di.created_at
FROM projects p
JOIN design_iterations di ON p.id = di.project_id
JOIN synthesis_results sr ON di.id = sr.iteration_id
WHERE sr.ii_achieved IS NOT NULL
ORDER BY p.type, sr.ii_achieved ASC, sr.latency_cycles ASC;

-- View: Rule effectiveness summary
CREATE OR REPLACE VIEW rule_effectiveness_summary AS
SELECT 
    r.id,
    r.rule_text,
    r.category,
    r.priority,
    re.project_type,
    re.times_applied,
    re.success_count,
    CASE 
        WHEN re.times_applied > 0 
        THEN (re.success_count::FLOAT / re.times_applied) * 100
        ELSE 0
    END as success_rate_percentage,
    re.avg_ii_improvement
FROM hls_rules r
LEFT JOIN rules_effectiveness re ON r.id = re.rule_id
ORDER BY success_rate_percentage DESC, r.priority DESC;

-- ==================== Comments ====================
COMMENT ON TABLE projects IS 'HLS design projects';
COMMENT ON TABLE hls_rules IS 'Reusable HLS optimization rules';
COMMENT ON TABLE design_iterations IS 'Each design attempt within a project';
COMMENT ON TABLE synthesis_results IS 'HLS synthesis outcomes';
COMMENT ON TABLE rules_effectiveness IS 'Track which rules actually work';
COMMENT ON TABLE design_patterns IS 'Proven design patterns for specific problems';

-- New field comments
COMMENT ON COLUMN design_iterations.user_reference_code IS '用户提供的参考代码（C/C++代码、pseudocode、算法描述、baseline实现）。如未提供则为NULL';
COMMENT ON COLUMN design_iterations.user_specification IS '用户的需求规格（性能目标、资源约束、数据类型要求等）。如未提供则为NULL';
COMMENT ON COLUMN design_iterations.reference_metadata IS '参考信息的元数据JSON格式，如：{"language": "c", "code_type": "baseline", "source": "user_provided", "has_pseudocode": false}。如未提供则为NULL';

-- ==================== 完成訊息 ====================
DO $$ 
BEGIN 
    RAISE NOTICE '✓ HLS Knowledge Base schema initialized (clean version - no sample data)';
END $$;
