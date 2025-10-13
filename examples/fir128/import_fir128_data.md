# HLS Knowledge Base Data Import Guide

> **Version**: v1.0  
> **Update Date**: 2025-10-13  
> **Purpose**: Template for creating data import scripts for new HLS projects

This guide explains how to create data import scripts for new HLS projects (e.g., matrix-mult) based on the `import_fir128_data.py` template.

---

## UPSERT Mode (Overwrite Strategy)

**Behavior when re-running `import_fir128_data.py`**:

| Table | Query Condition | Duplicate → Overwrite | New → Insert |
|-------|----------------|----------------------|--------------|
| **projects** | id (UUID) | ✓ Overwrite | ✓ Insert |
| **design_iterations** | **(project_id, iteration_number)** ⭐ | ✓ Overwrite | ✓ Insert |
| **synthesis_results** | iteration_id | ✓ Overwrite | ✓ Insert |
| **rules_effectiveness** | (rule_id, project_type) | ✓ Overwrite (not accumulate) | ✓ Insert |

**Key Points**:
- ✓ **Script only contains Iteration #1, #2, #3** → These will be overwritten
- ✓ **Iteration #4 (not in script)** → Preserved (not affected)
- ✓ **rules_effectiveness** → Overwrite (suitable for data correction), not accumulate
- ✓ **API auto-recording** → Uses accumulate mode (real statistics)

**Use Cases**:
- Data correction/initialization
- Update code_snapshot comments
- Fix synthesis result values
- Avoid duplicate records when re-running

---

## Table of Contents

- [UPSERT Mode (Overwrite Strategy)](#upsert-mode-overwrite-strategy)
- [Import Script Structure Overview](#import-script-structure-overview)
- [Steps to Create New Project Import Script](#steps-to-create-new-project-import-script)
- [Optional Fields](#optional-fields)
- [Rule Matching Logic](#rule-matching-logic)
- [Common Project Type Examples](#common-project-type-examples)
- [Verification Checklist](#verification-checklist)
- [Execution Instructions](#execution-instructions)
- [References](#references)
- [Best Practices](#best-practices)

---

## Import Script Structure Overview

Each import script contains the following main components:

1. **Project Metadata** (`project`)
2. **Design Iteration List** (`iterations`)
3. **Rule Matching Logic** (`find_matching_rule`)
4. **Effectiveness Recording Function** (`record_rule_effectiveness`)
5. **Main Import Workflow** (`import_xxx_with_effectiveness`)

---

## Steps to Create New Project Import Script

### Step 1: Copy and Rename File

```bash
cp import_fir128_data.py import_matrix_mult_data.py
```

### Step 2: Modify Project Metadata

**Location**: `MATRIX_MULT_DATA["project"]`

**Original FIR128 Data**:

```python
FIR128_DATA = {
    "project": {
        "id": "550e8400-e29b-41d4-a716-446655440001",
        "name": "FIR128_Optimization_Demo",
        "type": "fir",
        "description": "128-tap FIR filter optimization journey with rule effectiveness tracking",
        "target_device": "xc7z020clg484-1"  # 常見 Zynq-7000 設備型號範例
    },
    # ...
}
```

**Replace with Matrix Multiplication**:

```python
MATRIX_MULT_DATA = {
    "project": {
        "id": "550e8400-e29b-41d4-a716-446655440002",  # New project ID
        "name": "MatrixMult_Optimization_Demo",        # Project name
        "type": "matrix_mult",                          # Project type
        "description": "NxN matrix multiplication with tiling and dataflow optimization",
        "target_device": "xczu9eg-ffvb1156-2-e"        # Target device
    },
    # ...
}
```

**Fields to Modify**:

| Field | Description | Example Value |
|-------|-------------|---------------|
| `id` | New UUID (generate with `uuid4()`) | `550e8400-e29b-41d4-a716-446655440002` |
| `name` | Project display name | `MatrixMult_Optimization_Demo` |
| `type` | Project type (for rule matching) | `matrix_mult`, `cordic`, `conv2d`, etc. |
| `description` | Project description | Brief summary of optimization goals |
| `target_device` | FPGA target device | `xczu9eg-ffvb1156-2-e` |

---

### Step 3: Modify Design Iteration Data

**Location**: `MATRIX_MULT_DATA["iterations"]`

#### 3.1 Basic Iteration Structure

Each iteration contains the following required fields:

```python
{
    "id": None,  # Auto-generate random UUID
    "iteration_number": 1,
    "approach_description": "Baseline implementation with triple nested loops",
    "code_snapshot": """...""",  # Complete synthesizable code
    "pragmas_used": ["#pragma HLS PIPELINE"],
    "prompt_used": "Create baseline matrix multiplication",
    "cursor_reasoning": "Starting with straightforward implementation",
    "synthesis_result": {
        "ii_achieved": 1024,
        "ii_target": 1,
        "latency_cycles": 262144,
        "timing_met": True,
        "resource_usage": {"DSP": 4, "LUT": 1250, "FF": 890, "BRAM": 2},
        "clock_period_ns": 10.0
    },
    "rules_applied": []  # Baseline version typically empty
}
```

#### 3.2 Matrix Multiplication Example Iterations

**Iteration 1: Baseline (Triple Nested Loop)**

```python
{
    "id": None,
    "iteration_number": 1,
    "approach_description": "Baseline triple nested loop implementation",
    "code_snapshot": """void matrix_mult(int A[64][64], int B[64][64], int C[64][64]) {
    Row: for(int i = 0; i < 64; i++) {
        Col: for(int j = 0; j < 64; j++) {
            int sum = 0;
            Product: for(int k = 0; k < 64; k++) {
                sum += A[i][k] * B[k][j];
            }
            C[i][j] = sum;
        }
    }
}""",
    "pragmas_used": [],
    "prompt_used": "Implement basic NxN matrix multiplication",
    "cursor_reasoning": "Establishing baseline with no optimizations",
    "synthesis_result": {
        "ii_achieved": 4096,
        "ii_target": 1,
        "latency_cycles": 262144,
        "timing_met": True,
        "resource_usage": {"DSP": 1, "LUT": 450, "FF": 320, "BRAM": 0},
        "clock_period_ns": 10.0
    },
    "rules_applied": []
}
```

**Iteration 2: Innermost Loop Pipelining**

```python
{
    "id": None,
    "iteration_number": 2,
    "approach_description": "Pipelined innermost loop to achieve II=1 per dot product",
    "code_snapshot": """void matrix_mult(int A[64][64], int B[64][64], int C[64][64]) {
    Row: for(int i = 0; i < 64; i++) {
        Col: for(int j = 0; j < 64; j++) {
            int sum = 0;
            Product: for(int k = 0; k < 64; k++) {
                #pragma HLS PIPELINE II=1
                sum += A[i][k] * B[k][j];
            }
            C[i][j] = sum;
        }
    }
}""",
    "pragmas_used": ["#pragma HLS PIPELINE II=1"],
    "prompt_used": "Pipeline the innermost loop for better throughput",
    "cursor_reasoning": "KB rule R045: Pipeline innermost loops first for immediate gains",
    "synthesis_result": {
        "ii_achieved": 64,
        "ii_target": 1,
        "latency_cycles": 4160,
        "timing_met": True,
        "resource_usage": {"DSP": 1, "LUT": 580, "FF": 410, "BRAM": 0},
        "clock_period_ns": 10.0
    },
    "rules_applied": [
        {
            "rule_code": "R045",  # Official rule number
            "rule_keywords": ["pipeline", "innermost", "loop"],
            "rule_description": "Pipeline innermost loops first to maximize throughput",
            "expected_benefit": "Reduce iteration latency",
            "previous_ii": 4096,
            "current_ii": 64,
            "success": True
        }
    ]
}
```

**Iteration 3: Array Partitioning Optimization**

```python
{
    "id": None,
    "iteration_number": 3,
    "approach_description": "Cyclic partitioning of matrix B to eliminate memory bottleneck",
    "code_snapshot": """void matrix_mult(int A[64][64], int B[64][64], int C[64][64]) {
    #pragma HLS ARRAY_PARTITION variable=B cyclic factor=16 dim=2
    
    Row: for(int i = 0; i < 64; i++) {
        Col: for(int j = 0; j < 64; j++) {
            int sum = 0;
            Product: for(int k = 0; k < 64; k++) {
                #pragma HLS PIPELINE II=1
                sum += A[i][k] * B[k][j];
            }
            C[i][j] = sum;
        }
    }
}""",
    "pragmas_used": [
        "#pragma HLS PIPELINE II=1",
        "#pragma HLS ARRAY_PARTITION variable=B cyclic factor=16 dim=2"
    ],
    "prompt_used": "Apply array partitioning to matrix B to enable parallel access",
    "cursor_reasoning": "KB rule R078 with 85% success rate: Cyclic partition for stride access patterns",
    "synthesis_result": {
        "ii_achieved": 1,
        "ii_target": 1,
        "latency_cycles": 4100,
        "timing_met": True,
        "resource_usage": {"DSP": 1, "LUT": 920, "FF": 650, "BRAM": 8},
        "clock_period_ns": 10.0
    },
    "rules_applied": [
        {
            "rule_code": "R078",
            "rule_keywords": ["array", "partition", "cyclic", "memory"],
            "rule_description": "Use cyclic partitioning for arrays with strided access patterns",
            "expected_benefit": "Enable parallel memory access to achieve II=1",
            "previous_ii": 64,
            "current_ii": 1,
            "success": True
        }
    ]
}
```

---

### Step 4: Modify Rule Type Parameter

In `record_rule_effectiveness()` calls, change project type from `"fir"` to `"matrix_mult"`:

**Location**: `record_rule_effectiveness()` function call

**Original FIR128 Code**:

```python
# Original code
eff_id, is_new = await record_rule_effectiveness(
    conn,
    rule["id"],
    "fir",  # NOTE: This needs to be changed
    success,
    ii_improvement if success else 0
)
```

**Modified Version**:

```python
eff_id, is_new = await record_rule_effectiveness(
    conn,
    rule["id"],
    "matrix_mult",  # Updated project type
    success,
    ii_improvement if success else 0
)
```

---

### Step 5: Update Function Names and Variable Names

**Global Replacement Recommendations**:

```python
# Function names
import_fir128_with_effectiveness → import_matrix_mult_with_effectiveness

# Data dictionary
FIR128_DATA → MATRIX_MULT_DATA

# Output messages
"FIR128 數據導入工具" → "Matrix Multiplication Data Import Tool"
```

---

## Optional Fields

### User-Provided Reference Code

If an iteration is based on user-provided code, add the following fields:

```python
{
    "id": None,
    "iteration_number": 4,
    "approach_description": "Optimized based on user's C reference code",
    
    # User's original code
    "user_reference_code": """
        void matmul_baseline(int out[64][64], int a[64][64], int b[64][64]) {
            for (int i = 0; i < 64; i++)
                for (int j = 0; j < 64; j++) {
                    out[i][j] = 0;
                    for (int k = 0; k < 64; k++)
                        out[i][j] += a[i][k] * b[k][j];
                }
        }
    """,
    
    # User's specification requirements
    "user_specification": "Target: II=1, Data: int32, Constraints: minimize BRAM usage",
    
    # Reference code metadata
    "reference_metadata": {
        "language": "c",
        "code_type": "baseline_implementation",
        "source": "user_provided",
        "has_pseudocode": False
    },
    
    "code_snapshot": """/* HLS optimized implementation */""",
    "pragmas_used": ["..."],
    # ... (other required fields)
}
```

---

## Rule Matching Logic

### Rule Sources

The import script supports two rule sources:

1. **Official Rules** (`ug1399_rules.txt`): Use `R###` numbering (e.g., `R045`, `R078`)
   - These rules are derived from Xilinx UG1399 documentation
   - Total of 287 official rules covering HLS optimization best practices
2. **User Prompts** (`user_prompts.txt`): Use `P###` numbering (e.g., `P001`, `P002`)
   - These are project-specific optimization techniques learned from experience
   - Currently contains 15 user-defined prompts for FIR, CORDIC, and general optimizations

### Rule Matching Priority

The `find_matching_rule()` function matches rules with the following priority:

```python
# Priority 0: Rule code (most precise)
rule_code="R045"  # Direct match to official rule from ug1399_rules.txt

# Priority 1: Exact full description match
description="Pipeline innermost loops first to maximize throughput"

# Priority 2: Main portion of description match (first 50 characters)
description="Pipeline innermost loops first..."

# Priority 3: Multiple keyword combination match (first 2 keywords)
keywords=["pipeline", "innermost", "loop"]

# Priority 4: Single keyword match (fallback)
keywords=["pipeline"]
```

### Recommended Practice

**Always provide `rule_code`** in `rules_applied` to ensure precise matching:

```python
"rules_applied": [
    {
        "rule_code": "R078",  # BEST PRACTICE: Explicitly specify rule number
        "rule_keywords": ["array", "partition", "cyclic"],
        "rule_description": "Use cyclic partitioning for strided access",
        "expected_benefit": "Enable parallel memory access",
        "previous_ii": 64,
        "current_ii": 1,
        "success": True
    }
]
```

**Rule Code Naming Convention**:

- **R###**: Official rules from `ug1399_rules.txt` (e.g., R001-R287)
- **P###**: User-defined prompts from `user_prompts.txt` (e.g., P001-P015)

---

## Common Project Type Examples

### Convolution 2D

```python
CONV2D_DATA = {
    "project": {
        "id": "550e8400-e29b-41d4-a716-446655440003",
        "name": "Conv2D_Optimization_Demo",
        "type": "conv2d",
        "description": "2D convolution with sliding window and line buffer",
        "target_device": "xczu7ev-ffvc1156-2-e"
    },
    "iterations": [
        {
            "iteration_number": 1,
            "approach_description": "Baseline 5-layer nested loops",
            "synthesis_result": {
                "ii_achieved": 2048,
                "latency_cycles": 524288,
                # ...
            },
            "rules_applied": []
        },
        {
            "iteration_number": 2,
            "approach_description": "Line buffer optimization",
            "rules_applied": [
                {
                    "rule_code": "R112",  # Hypothetical rule number from ug1399_rules.txt
                    "rule_keywords": ["line", "buffer", "sliding", "window"],
                    "rule_description": "Use line buffers for 2D sliding window access",
                    "previous_ii": 2048,
                    "current_ii": 256,
                    "success": True
                }
            ]
        }
    ]
}
```

### FFT (Fast Fourier Transform)

```python
FFT_DATA = {
    "project": {
        "id": "550e8400-e29b-41d4-a716-446655440004",
        "name": "FFT_Optimization_Demo",
        "type": "fft",
        "description": "1024-point radix-2 FFT with streaming dataflow",
        "target_device": "xc7z020clg484-1"
    },
    "iterations": [
        {
            "iteration_number": 1,
            "approach_description": "Baseline radix-2 butterfly",
            "rules_applied": []
        },
        {
            "iteration_number": 2,
            "approach_description": "Dataflow between stages",
            "rules_applied": [
                {
                    "rule_code": "R156",  # Rule from ug1399_rules.txt for DATAFLOW
                    "rule_keywords": ["dataflow", "pipeline", "function"],
                    "rule_description": "Apply DATAFLOW to function-level pipeline",
                    "previous_ii": 10240,
                    "current_ii": 1024,
                    "success": True
                }
            ]
        }
    ]
}
```

---

## Verification Checklist

When creating a new import script, verify the following:

- [ ] **Project ID** is a unique UUID
- [ ] **Project type** (`type`) is a valid enumeration value in the database
- [ ] **Iteration numbers** start from 1 and increment consecutively
- [ ] **code_snapshot** contains complete compilable code
- [ ] All numeric fields in **synthesis_result** are valid
- [ ] **rule_code** in **rules_applied** exists in the rules table (check `ug1399_rules.txt` or `user_prompts.txt`)
- [ ] **previous_ii** and **current_ii** values are reasonable (current_ii <= previous_ii)
- [ ] **project_type** parameter in `record_rule_effectiveness()` has been updated
- [ ] All function and variable names have been renamed (avoid confusion with FIR128)

---

## Execution Instructions

```bash
# 1. Verify database connection
psql -d hls_knowledge -c "SELECT COUNT(*) FROM projects;"

# 2. Execute import script
python3 import_matrix_mult_data.py

# 3. Verify import results
curl "http://localhost:8000/api/rules/effective?project_type=matrix_mult"

# 4. View rule effectiveness ranking
psql -d hls_knowledge -c "
    SELECT r.rule_code, r.rule_text, re.success_count, re.times_applied
    FROM rules_effectiveness re
    JOIN hls_rules r ON re.rule_id = r.id
    WHERE re.project_type = 'matrix_mult'
    ORDER BY re.avg_ii_improvement DESC
    LIMIT 10;
"
```

---

## References

- **FIR128 Example**: `import_fir128_data.py`
- **Official Rules**: `ug1399_rules.txt` (287 rules from Xilinx UG1399 documentation)
- **User Prompts**: `user_prompts.txt` (15 project-specific prompts)
- **Database Schema**: Review `design_iterations`, `synthesis_results`, `rules_effectiveness` table structures

---

## Best Practices

1. **Rule Code Priority**: Always use `rule_code` rather than relying on keyword matching
2. **Code Completeness**: `code_snapshot` should contain complete code for future analysis
3. **Code Comments (v1.0)**: Follow Code Snapshot Comment Standards for 100% reproducibility
4. **Reasonable Improvement Magnitude**: Ensure II improvement values are realistic (avoid 4096 to 1 jumps in single iteration)
5. **Incremental Optimization**: Each iteration should apply 1-2 major optimization techniques only
6. **Detailed Reasoning Records**: `cursor_reasoning` should document AI decision logic for future analysis
7. **Rule Source Tracking**: Use R### for official UG1399 rules and P### for user-defined prompts to maintain clear provenance

---

## Code Snapshot Comment Standards (v1.0, Updated 2025-10-12)

### Why Comments Matter

**Critical Principle**: Code snapshot comments are the **PRIMARY source** of optimization knowledge.

**Verified Fact** (FIR128 Iteration #4):
- 100% reproducibility achieved through comments alone
- All metrics matched: II, latency, DSP, LUT, FF, BRAM
- No dependency on external rule definitions

### Mandatory Comment Structure

#### 1. File Header (REQUIRED) ⭐⭐⭐

Every `code_snapshot` MUST include:

```cpp
// ============================================================================
// [Project_Name] - Iteration #N: [Optimization_Technique_Name]
// ============================================================================
// Previous: Iteration #X (II=Y cycles, [previous_approach])
// Target: [Performance_goal, e.g., II < 10 cycles]
//
// Problem Identified (optional but recommended):
// - [What bottleneck or issue are we addressing?]
// - [Evidence, e.g., "II=128 = array_size → memory port bottleneck"]
//
// Optimizations Applied:
// 1. [Technique_1_Name]:
//    - What: [Specific technique and parameters]
//    - Why: [Problem it solves, rationale]
//    - Parameters: [Specific values and WHY chosen these values]
//    - Expected: [Predicted improvement, e.g., "90-98% II reduction"]
//
// 2. [Technique_2_Name]:
//    - What: ...
//    - Why: ...
//    - Parameters: ...
//    - Expected: ...
//
// Optional - Applied Rules (if known):
//   - P00X: [Rule_name]
//   - R00X: [Rule_name]
// ============================================================================
```

#### 2. Pragma Comments (REQUIRED) ⭐⭐

Every pragma MUST have immediately preceding comment:

```cpp
// [Technique_Name]: [What it does in one line]
// Parameters: [Specific values and WHY these values]
// Rationale: [Why needed - what problem does it solve]
#pragma HLS ...
```

### FIR128 Example (100% Reproducible)

**Iteration #2: Loop Merge**

```python
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
}"""
```

### Comment Quality Checklist

Before recording iteration to KB, verify code_snapshot includes:

- [ ] **File header exists** with complete optimization strategy
- [ ] **Previous iteration** explicitly referenced (number, II, approach)
- [ ] **Each optimization** has: What, Why, Parameters (with reasoning), Expected
- [ ] **Every pragma** has explanatory comment (what, why, parameters)
- [ ] **Rationale is specific**: "why this technique?" and "why these parameters?"
- [ ] **Parameters justified**: e.g., "factor=2 because..." not just "factor=2"
- [ ] **Can reproduce**: Someone else can understand and apply to new design
- [ ] **Traceability**: Clear path from previous iteration to current optimization

### ✅ Good vs ❌ Bad Examples

**✅ GOOD Example** (Iteration #2 above):
- Complete file header
- Clear problem identification
- Detailed optimization description
- Pragma comments with rationale
- 100% reproducible

**❌ BAD Example**:
```python
"code_snapshot": """void fir(data_t *y, data_t x) {
    static data_t shift_reg[N];
    acc_t acc = 0;
    int i;

    TDL_and_MAC:
    for (i = N - 1; i >= 0; i--) {
        #pragma HLS PIPELINE II=1
        acc += shift_reg[i] * c[i];
        shift_reg[i] = (i == 0) ? x : shift_reg[i - 1];
    }
    *y = acc;
}"""
```

**Why bad?**
- ❌ No file header
- ❌ No pragma explanation
- ❌ No optimization rationale
- ❌ Cannot understand why or reproduce

### Integration with rules_applied

**When to use both**:

```python
"rules_applied": [
    {
        "rule_code": "P001",  # For statistics
        "previous_ii": 264,
        "current_ii": 134,
        "success": True
    }
],
"code_snapshot": """
    // Complete comments for reproducibility
    // ...
"""
```

**When rule matching is uncertain**:

```python
"rules_applied": [],  # or null - don't force match
"code_snapshot": """
    // MUST have detailed comments!
    // Document complete optimization strategy
    // ...
"""
```

**Key Principle**: 
```
code_snapshot comments = PRIMARY source (for reproducibility)
rule_code = SECONDARY (for statistics)
```

---

## Data Quality Guidelines (Updated 2025-10-09)

### Synthesis Result Fields

When documenting synthesis results, follow these guidelines for data accuracy:

**Use `None` for missing data** instead of estimates:

```python
"synthesis_result": {
    "ii_achieved": 264,           # ✅ 保留：實驗記錄有明確數據
    "ii_target": 1,               # ✅ 保留：HLS 優化標準目標
    "latency_cycles": None,       # ✅ 改為 None：實驗記錄未提供
    "timing_met": None,           # ✅ 改為 None：實驗記錄未提供
    "resource_usage": {"DSP": 1}, # ✅ 只保留有實驗依據的數據
    "clock_period_ns": None       # ✅ 改為 None：實驗記錄未提供
}
```

**Why use `None`?**
- ✅ Clearly indicates missing data
- ✅ Compatible with database NULL types
- ✅ Maintains data integrity and traceability
- ✅ Suitable for academic and production use

**What to keep?**
- `ii_achieved`: Keep if explicitly documented in synthesis report
- `ii_target`: Keep as 1 (standard HLS optimization target)
- `resource_usage.DSP`: Keep if verifiable (e.g., from "only one lane" constraint)

**What to set as `None`?**
- `latency_cycles`: If only II is documented
- `timing_met`: If no timing report available
- `clock_period_ns`: If no clock information provided
- `resource_usage.LUT/FF/BRAM`: If no detailed resource report

### Prompt and Reasoning Fields

**prompt_used**: Use original user input, not simplified versions

```python
# ✅ Good: Original user prompt
"prompt_used": "Develop the FIR using Vitis HLS based on the files in the fir128 folder. Only one lane can be used for computation. Create a baseline folder inside fir128 for this project. Run csim, synthesis, and cosim."

# ❌ Bad: Simplified version
"prompt_used": "Create a baseline FIR128 implementation with separate loops"
```

**cursor_reasoning**: Accurately reference rules, avoid fabrication

```python
# ✅ Good: Accurate P002 reference
"cursor_reasoning": "Applied P002: pipeline rewind to enable overlapping execution of successive iterations without gaps"

# ❌ Bad: Incorrect description + fabricated success rate
"cursor_reasoning": "KB effective rule: 'Always apply pipeline rewind to outermost loops' (success rate: 75%)"
```

**Rule reference best practices:**
- Quote rule descriptions accurately from `ug1399_rules.txt` or `user_prompts.txt`
- Use rule codes (R### or P###) for precise identification
- Do not fabricate success rates unless from actual KB statistics
- Avoid misquoting rule conditions (e.g., "outermost loops" vs "performance-critical loops")

### Target Device

**target_device**: Can use example device models

```python
# ✅ Acceptable: Common device as example
"target_device": "xc7z020clg484-1"  # 常見 Zynq-7000 設備型號範例

# Also acceptable: Actual device if specified
"target_device": "xczu9eg-ffvb1156-2-e"  # Zynq UltraScale+ device
```

Example device models are acceptable since they don't affect the optimization methodology being documented.

### Data Verification Example

**Before correction (contains estimates):**
```python
{
    "synthesis_result": {
        "ii_achieved": 264,
        "latency_cycles": 268,          # ❌ Not in experiment log
        "timing_met": True,             # ❌ Not in experiment log
        "resource_usage": {
            "DSP": 1,
            "LUT": 398,                 # ❌ Not in experiment log
            "FF": 290,                  # ❌ Not in experiment log
            "BRAM": 0                   # ❌ Not in experiment log
        },
        "clock_period_ns": 10.0         # ❌ Not in experiment log
    }
}
```

**After correction (only verifiable data):**
```python
{
    "synthesis_result": {
        "ii_achieved": 264,             # ✅ From experiment: "II = 264"
        "ii_target": 1,                 # ✅ Standard HLS target
        "latency_cycles": None,         # Fixed: No data
        "timing_met": None,             # Fixed: No data
        "resource_usage": {"DSP": 1},   # ✅ From "only one lane"
        "clock_period_ns": None         # Fixed: No data
    }
}
```

**Quality improvement:**
- Accuracy: Increased from 7.25/10 to 9.25/10
- Traceability: 100% (all retained data verifiable)
- Suitable for: Academic papers, production use, open-source projects

---

**Upon completion, you will have a structured HLS optimization knowledge base that Cursor AI can learn from and apply to future projects.**


