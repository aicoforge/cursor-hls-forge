# cursor-hls-forge

> **AI + Knowledge Base = Fast HLS Optimization**
> Stop guessing. Start learning. 15-minute iterations instead of weeks of trial-and-error.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Platform](https://img.shields.io/badge/Platform-Xilinx%20HLS-blue.svg)](https://www.xilinx.com/)
[![Vitis HLS](https://img.shields.io/badge/Vitis%20HLS-2022.1-green.svg)](https://www.xilinx.com/products/design-tools/vitis.html)

## What Is This?

**AICOFORGE's second open-source project!** After cursor-fpga-forge (FPGA verification), we're tackling HLS optimization.

**The Big Idea**: AI is creative but forgetful. What if your AI could remember every successful optimization and learn from past designs? That's what we built.

**What You Get**: A knowledge base that captures what works. Query it before optimizing. Record results automatically. Build permanent knowledge that makes every design faster.

**Tech Stack**: Cursor IDE + PostgreSQL Knowledge Base + 287 HLS Rules + Your Design Experience

## The Problem

**HLS optimization is painful**:
- Try pragma → fail → try another → fail → repeat 50 times
- AI gives different answers every time (inconsistent)
- No memory of what worked before
- Can't learn from past projects
- Weeks wasted on random experiments

**Sound familiar?** Yeah, we've been there too.

## Our Solution

**Stop guessing. Start learning.**

Instead of hoping AI remembers, we built a system that **never forgets**:
- Query what worked for similar designs
- Apply proven optimization patterns
- Auto-record every result
- Build knowledge that lasts forever

**Result**: 15 minutes per iteration. Systematic progress. No more random trial-and-error.

<div align="center">

**Real Example: FIR128 Filter**

| What We Did | II Result | Time |
|-------------|-----------|------|
| Baseline design | 264 cycles | 15 min |
| Query KB → merge loops | 134 cycles (-49%) | 15 min |
| Query KB → pipeline rewind | 128 cycles (-52%) | 15 min |
| Apply array partition | 2 cycles (-99%) ★ | 15 min |

**1 hour total. 132x faster. All knowledge saved for next time.**

</div>

## How It Works

### Old Way (Weeks of Pain)
```
Try random pragma → Synthesize → Doesn't work → Try another →
Doesn't work → Google it → Try again → Maybe works? → Repeat...

✘ No memory
✘ Random guessing
✘ Weeks wasted
```

### New Way (15 Min Per Iteration)
```
1. Ask KB: "What worked before?"
2. Apply proven patterns
3. Synthesize
4. Auto-save results
5. Repeat with smarter suggestions

✓ Learns from every design
✓ Systematic progress
✓ Fast iterations
```

## Important Notes

### [!] Current System Maturity

**What Works Great** (Available Now):
- ✓ Recording design iterations with full context
- ✓ Querying similar designs and their results
- ✓ Auto-parsing synthesis reports
- ✓ 287 official Vitis HLS rules in database

**What Needs Your Help** (Growing):
- [!] User-contributed optimization patterns (currently: P001, P002)
- [!] Project-specific rules library (you build as you design)
- [!] Advanced diagnostic patterns (under development)

**Key Insight from Testing**:
- The FIR128 example shows the **full potential** of the system
- Iterations #1-#3 rules (P001, P002) are in the KB ✓
- Iteration #4 breakthrough (array partition) requires adding your experience
- **This is by design**: The KB learns from YOUR successful optimizations

**Think of it as**:
- Start with 287 general rules
- Add 2-3 proven patterns (P001, P002, etc.)
- **You contribute** breakthrough techniques as you discover them
- System gets smarter with every project

## What You Record

**Super simple** - just the basics:

**Each Design**:
- What you tried (approach description)
- Your code (full implementation)
- Results (II, latency, resources)
- Why you tried it (your reasoning)

**That's it.** The system handles:
- Performance tracking
- Pattern recognition
- Smart suggestions
- Historical comparisons

**The More You Use It, The Smarter It Gets.**

## Live Demo: FIR128 Story

Watch how we went from 264 cycles to 2 cycles in four 15-minute steps:

### Step 1: Baseline (II=264)
```cpp
// Two loops - shift then MAC
for (int i = 127; i > 0; i--)
    shift_reg[i] = shift_reg[i-1];

for (int i = 0; i < 128; i++)
    acc += shift_reg[i] * c[i];
```
**Result**: Slow. But now we have a baseline.

### Step 2: Query KB → Merge Loops (II=134, -49%)
```bash
# Ask: "What works for FIR?"
# KB says: "Merge loops" (Rule P001, 100% success rate)
```
```cpp
// One merged loop
for (int i = 127; i >= 0; i--) {
    acc += shift_reg[i] * c[i];
    shift_reg[i] = (i == 0) ? x : shift_reg[i-1];
}
```
**Result**: 49% faster in 15 minutes. ✓ KB guided this!

### Step 3: Query KB → Pipeline Rewind (II=128, -52%)
```bash
# Ask: "How to improve pipelined FIR?"
# KB says: "Add rewind pragma" (Rule P002)
```
```cpp
for (int i = 127; i >= 0; i--) {
    #pragma HLS PIPELINE II=1 rewind  // ← One word change!
    acc += shift_reg[i] * c[i];
    shift_reg[i] = (i == 0) ? x : shift_reg[i-1];
}
```
**Result**: Better. But II=128 for 128-tap? That's weird... ✓ KB guided this!

### Step 4: Breakthrough Moment (II=2, -99%!)
```bash
# Pattern Recognition: II=128, Tap count=128
# Diagnosis: Memory port bottleneck!
# Solution: Array partition (learned from HLS expertise)
```
```cpp
static data_t shift_reg[128];
#pragma HLS ARRAY_PARTITION variable=shift_reg cyclic factor=2

for (int i = 127; i >= 0; i--) {
    #pragma HLS PIPELINE II=1 rewind
    #pragma HLS UNROLL factor=2
    acc += shift_reg[i] * c[i];
    shift_reg[i] = (i == 0) ? x : shift_reg[i-1];
}
```
**Result**: From 264 to 2 cycles. Done.

**What Happened Here**:
- Steps 1-3: ✓ KB provided systematic guidance
- Step 4: Identified pattern (II=tap count), applied HLS expertise
- **After Step 4**: This breakthrough is NOW in your KB for future FIR designs

**Total time**: 1 hour
**Future FIR designs**: Will have array partition in KB (30 min instead of weeks!)

## Quick Start

**Demo Video**: [Watch cursor + HLS design demo](https://www.youtube.com/watch?v=gq86lMYehMU) - 15-minute optimization walkthrough

## User & Cursor Interaction Examples

### Example 1. Knowledge Base Query (Click to expand):

<details>
<summary>💬 <b>Example Conversation: Query FIR Design Iterations</b></summary>

---

**👤 User**:
> Please list all fir design iterations from the knowledge base

---

**🤖 Cursor**:
> I'll help you query the FIR design iterations from the knowledge base.
>
> First, let me connect to the knowledge base API:

```bash
curl -s "http://localhost:8000/api/design/similar?project_type=fir&limit=20" | jq '.'
```

```json
{
  "query": {
    "project_type": "fir",
    "target_ii": null,
    "limit": 20
  },
  "results": [
    {
      "iteration_id": "310f81d0-4040-4b82-809b-1bce2344bcb2",
      "project_id": "550e8400-e29b-41d4-a716-446655440001",
      "project_name": "FIR128_Optimization_Demo",
      "project_type": "fir",
      "iteration_number": 4,
      "approach_description": "Applied array partition (cyclic factor=2) and partial unroll (factor=2)",
      "pragmas_used": [
        "#pragma HLS ARRAY_PARTITION variable=shift_reg cyclic factor=2 dim=1",
        "#pragma HLS PIPELINE II=1 rewind",
        "#pragma HLS UNROLL factor=2"
      ],
      "ii_achieved": 2,
      "latency_cycles": 131,
      "resource_usage": "{\"FF\": 220, \"DSP\": 2, \"LUT\": 314, \"BRAM_18K\": 3}",
      "created_at": "2025-10-13T11:19:27.596009"
    },
    {
      "iteration_id": "3c9bd6f4-5ae3-4761-aa91-f144b978df02",
      "project_name": "FIR128_Optimization_Demo",
      "iteration_number": 3,
      "approach_description": "Applied pipeline rewind optimization to merged loop",
      "pragmas_used": ["#pragma HLS PIPELINE II=1 rewind"],
      "ii_achieved": 128,
      "created_at": "2025-10-10T18:56:38.347312"
    },
    {
      "iteration_id": "95aa91cf-a5cc-43da-adaa-437698b62bf1",
      "project_name": "FIR128_Optimization_Demo",
      "iteration_number": 2,
      "approach_description": "Merged shift and MAC into single loop using ternary operator",
      "pragmas_used": ["#pragma HLS PIPELINE II=1"],
      "ii_achieved": 134,
      "created_at": "2025-10-08T18:56:38.347312"
    },
    {
      "iteration_id": "3e0a7fdd-8ceb-4912-a5fa-5d4ff3f65676",
      "project_name": "FIR128_Optimization_Demo",
      "iteration_number": 1,
      "approach_description": "Baseline design with separate shift and MAC loops",
      "pragmas_used": ["#pragma HLS PIPELINE II=1"],
      "ii_achieved": 264,
      "created_at": "2025-10-06T18:56:38.347312"
    }
  ]
}
```

> Perfect! Successfully queried FIR design iterations from the knowledge base. Here's the complete list:

---

## 📊 FIR Design Iterations in Knowledge Base

**Project**: `FIR128_Optimization_Demo`
**Project ID**: `550e8400-e29b-41d4-a716-446655440001`
**Total Iterations**: **4**

---

### 🏆 Iteration #4 (Best Performance) ⭐

- **Iteration ID**: `310f81d0-4040-4b82-809b-1bce2344bcb2`
- **II Achieved**: **2 cycles** ✨
- **Target II**: 1 cycle
- **Latency**: 131 cycles
- **Optimization Approach**: Array partition (cyclic factor=2) + Partial unroll (factor=2)
- **Pragmas**:
  ```cpp
  #pragma HLS INTERFACE ap_none port=y
  #pragma HLS INTERFACE ap_none port=x
  #pragma HLS ARRAY_PARTITION variable=shift_reg cyclic factor=2 dim=1
  #pragma HLS PIPELINE II=1 rewind
  #pragma HLS UNROLL factor=2
  ```
- **Resource Usage**:
  - DSP: 2
  - LUT: 314
  - FF: 220
  - BRAM_18K: 3
- **Created**: 2025-10-13

---

### 📈 Iteration #3

- **Iteration ID**: `3c9bd6f4-5ae3-4761-aa91-f144b978df02`
- **II Achieved**: 128 cycles
- **Target II**: 1 cycle
- **Optimization Approach**: Pipeline rewind optimization to merged loop
- **Pragmas**:
  ```cpp
  #pragma HLS PIPELINE II=1 rewind
  ```
- **Resource Usage**: DSP: 1
- **Created**: 2025-10-10

---

### 📈 Iteration #2

- **Iteration ID**: `95aa91cf-a5cc-43da-adaa-437698b62bf1`
- **II Achieved**: 134 cycles
- **Target II**: 1 cycle
- **Optimization Approach**: Merged shift and MAC into single loop using ternary operator
- **Pragmas**:
  ```cpp
  #pragma HLS PIPELINE II=1
  ```
- **Resource Usage**: DSP: 1
- **Created**: 2025-10-08

---

### 📊 Iteration #1 (Baseline)

- **Iteration ID**: `3e0a7fdd-8ceb-4912-a5fa-5d4ff3f65676`
- **II Achieved**: 264 cycles
- **Target II**: 1 cycle
- **Optimization Approach**: Baseline design with separate shift and MAC loops
- **Pragmas**:
  ```cpp
  #pragma HLS PIPELINE II=1
  ```
- **Resource Usage**: DSP: 1
- **Created**: 2025-10-06

---

## 📉 Performance Improvement Journey

```
Iteration #1 (Baseline):          II = 264 cycles ████████████████████████████████████████████
          ↓ (-49.2%)
Iteration #2 (Loop Merge):        II = 134 cycles ██████████████████████
          ↓ (-4.5%)
Iteration #3 (Pipeline Rewind):   II = 128 cycles █████████████████████
          ↓ (-98.4%) 🚀
Iteration #4 (Array Partition):   II = 2 cycles   █

Total Improvement: 264 → 2 cycles (-99.2%)
```

---

## 🔑 Key Optimization Techniques Summary

| Iteration | Optimization Technique | II Improvement | Performance Gain |
|-----------|------------------------|----------------|------------------|
| **#2** | Loop Merge | 264 → 134 | -49.2% |
| **#3** | Pipeline Rewind | 134 → 128 | -4.5% |
| **#4** | Array Partition + Unroll | 128 → 2 | **-98.4%** 🏆 |

---

## 🎯 Optimization Techniques Explained

### 1️⃣ Loop Merge (Iteration #2)
- **Technique**: Used ternary operator to merge shift and MAC into a single loop
- **Effect**: Eliminated loop overhead, reduced by 130 cycles
- **Use Case**: When multiple related loops can be merged

### 2️⃣ Pipeline Rewind (Iteration #3)
- **Technique**: Enabled pipeline rewind optimization for bounded loops
- **Effect**: Enabled overlapping execution of iterations, reduced by 6 cycles
- **Use Case**: Pipeline optimization for loops with known bounds

### 3️⃣ Array Partition + Unroll (Iteration #4) ⭐
- **Technique**: Memory partitioning (cyclic factor=2) + Loop unrolling (factor=2)
- **Effect**: Broke through memory bottleneck, 128 → 2 cycles (**-98.4%**)
- **Key Point**: Partition factor must match unroll factor to achieve optimal results
- **Use Case**: When II value is close to array size (memory port bottleneck)

---

**🤖 Cursor**:
> 💡 **If you want to further optimize or create new FIR designs**:
>
> 1. **Reference Iteration #4** - Already achieved II=2 (close to theoretical best of II=1)
> 2. **Learn Best Practices** - Array partition + Unroll combination is highly effective for memory-intensive designs
> 3. **View Complete Code**:
>    ```bash
>    curl "http://localhost:8000/api/design/310f81d0-4040-4b82-809b-1bce2344bcb2/code" | jq -r '.code_snapshot'
>    ```
>
> 4. **Golden Rule**: When using Array Partition, the Unroll factor should match the Partition factor (e.g., both set to 2) to fully utilize memory bandwidth
>
> Would you like me to help you view the complete code for any specific iteration or create a new optimized version?

---

</details>

---

### What You Need
```bash
- Cursor IDE (free)
- Vitis HLS 2022.1+
- Python 3.8+
- PostgreSQL (we help you set up)
```

### Setup (5 minutes)
```bash
# Get the code
git clone https://github.com/aicoforge/cursor-hls-forge.git
cd cursor-hls-forge

# Start knowledge base
cd knowledge_base
./setup_kb.sh
python api_server.py  # Runs on localhost:8000

# Create your project
mkdir my_design
cd my_design
cp ../templates/.cursorrules .  # Tells Cursor about KB
cursor .  # Open in Cursor
```

### Your First Optimization (15 minutes)
```bash
# In Cursor, just say:
"Query KB for FIR designs and create optimized version"

# Cursor will:
1. Check KB for similar designs ✓
2. Apply proven patterns ✓
3. Generate optimized code ✓
4. Run synthesis (you approve) ✓
5. Save results to KB ✓

# Next iteration: Query KB again with new context
# Each iteration: 15 minutes, builds on proven knowledge
```

## Time Breakdown

### What AI + KB Do (Fast)
- **Query designs**: Instant
- **Apply patterns**: Seconds
- **Generate code**: Seconds
- **Parse results**: Seconds
- **Save to KB**: Seconds

### What HLS Does (Normal Speed)
- **Synthesis**: 30 seconds to 5 minutes
- **Analysis**: Few seconds

**Bottom Line**: 15 minutes per iteration instead of days/weeks of guessing.

### Real Numbers: FIR128
```
Iteration 1 (Baseline):       15 min → II=264
Iteration 2 (Loop merge):     15 min → II=134 (-49%) [KB Rule P001]
Iteration 3 (Pipeline):       15 min → II=128 (-52%) [KB Rule P002]
Iteration 4 (Partition):      15 min → II=2 (-99%)   [Your Breakthrough]

Total: 1 hour, 132x speedup, permanent knowledge created
```

## Knowledge Base (Simple Version)

**You don't need to understand databases.** Just know:

**When You Ask**:
```
"Show me FIR optimizations"
→ Get proven approaches with real results
→ See what worked and why
```

**When You Save**:
```
After synthesis:
→ Results auto-saved
→ Compared with previous tries
→ Available for future projects
```

**What You Get**:
- Search by type (FIR, FFT, matrix, etc.)
- Filter by performance
- Sort by success rate
- Compare iterations

**What Grows Over Time**:
- More projects → More patterns
- More rules → Better suggestions
- More history → Smarter AI

## Customization

### Different Tools?
```bash
# Edit tool configuration
VITIS_VERSION="2023.2"  # Change version
```

### Different Device?
```bash
# In your TCL file
set_part {xcvu9p-flga2104-2-i}  # Use your device
```

### Private KB?
```bash
# Run on your server for privacy
KB_API="http://your-server.company.com:8000"
# All data stays private
```

## Tech Stack

**AI Side**:
- Cursor IDE (any AI works)
- Knowledge Base API (Python)
- Auto parsing and recording

**HLS Side**:
- Vitis HLS 2022.1+ (or Vivado HLS)
- Xilinx devices (any family)
- Cross-version support

**Knowledge Base**:
- PostgreSQL (fast, reliable)
- 287 official HLS rules (from Xilinx UG1399)
- User patterns (P001, P002, ... grows as you design)
- Your project history

## Roadmap

**Now** (Available Today):
- ✓ Knowledge Base with 287 HLS rules
- ✓ Design iteration recording
- ✓ Similar design query
- ✓ Auto synthesis parsing
- ✓ Basic user rules (P001, P002)

**Soon** (Next 3-6 months):
- Enhanced rule suggestion engine
- Pattern recognition AI
- Web dashboard for KB browsing
- Team collaboration features
- Expanded user rules library (community contributions)

**Later** (6-12 months):
- Predictive optimization (AI predicts which rules will work)
- Auto pragma generation from descriptions
- Resource-aware optimization
- Cross-platform knowledge transfer
- Advanced diagnostic patterns

## Why This Matters

**Engineers waste 60-80% of time on**:
- ✘ Random pragma trials
- ✘ Repeating old mistakes
- ✘ Forgetting what worked
- ✘ Inconsistent AI answers

**With KB + AI**:
- ✓ Query proven solutions first
- ✓ Build permanent knowledge
- ✓ Learn from every design
- ✓ Consistent, reproducible results

**Business Impact**:
- Weeks → Hours for optimization
- Knowledge survives turnover
- Every project helps future projects
- Less trial-and-error waste

**Community Impact**:
- Share successful patterns (optional)
- Build collective HLS knowledge
- Help others avoid your mistakes
- Accelerate everyone's designs

## Real Results

**Challenge**: Optimize 128-tap FIR for minimum II

**Old Way** (Weeks):
- Week 1: Random pragma experiments
- Week 2: Debug why still slow
- Week 3: Maybe discover loop merge
- Week 4+: Still searching for solution

**Our Way** (1 Hour):
- Hour 1: Systematic KB-driven optimization
  - 15 min: Baseline (establish starting point)
  - 15 min: Loop merge (KB suggested via P001)
  - 15 min: Pipeline rewind (KB suggested via P002)
  - 15 min: Array partition (diagnosed & applied)
- **Result**: 132x faster, all knowledge saved

**Next FIR Design**: Will start with all 4 techniques in KB!

## Use Cases

Perfect for:

**Communication**:
- FIR/IIR filters
- FFT implementations
- Error correction codes

**Signal Processing**:
- Image processing
- Radar algorithms
- Software-defined radio

**Computing**:
- Matrix operations
- Neural networks
- Numerical simulations

**Finance**:
- Option pricing
- Risk calculations
- Market data processing

## Services & Support

### Commercial Services

We offer **AI + HLS optimization consulting** at [aicoforge.com](https://aicoforge.com):

**What We Do**:
- Enterprise KB setup (your private cloud)
- Custom rule creation (seed your KB with domain expertise)
- Design optimization services
- Team training
- Private LLM integration

Contact: kevinjan@aicoforge.com

### Open Source

**We need your help**:
- Share successful patterns (if you can)
- Contribute HLS rules
- Report what works
- Help others learn

**This works better when we all share knowledge.**

## Connect

- **Website**: [aicoforge.com](https://aicoforge.com)
- **Mission**: Make HLS optimization systematic, not random
- **Email**: kevinjan@aicoforge.com

**Join us in building the world's HLS knowledge base.** Every design you record helps everyone.

---

## FAQ

**Q: Do I have to record everything?**  
A: No. But recording helps future you (and others).

**Q: Is my data private?**  
A: Yes. You control the KB. Run it anywhere. Share what you want.

**Q: I use Vivado HLS, not Vitis. Works?**  
A: Yes. Just change tool paths in config.

**Q: Can I use ChatGPT instead of Cursor?**  
A: Sure. The KB works with any AI. Use what you like.

**Q: How much storage?**  
A: Tiny. ~10-50KB per design. 1000 designs = ~50MB.

**Q: My design is totally different. Still useful?**  
A: Yes. Start with 287 general rules, then build your domain knowledge.

**Q: Can I reproduce the FIR128 results exactly?**  
A: Iterations #1-#3 are fully reproducible (rules P001, P002 in KB).
Iteration #4 requires adding array partition knowledge to your KB first.
This is intentional - the system learns from YOUR breakthroughs.

**Q: What if KB doesn't have the rule I need?**  
A: That's when YOU discover it! Apply your HLS expertise, record the success,
and now your KB has that knowledge forever. Next project starts smarter.

**Q: How do I add my own rules?**  
A: After a successful optimization, document it as a user rule (P003, P004, etc.).
Use the provided SQL scripts or API endpoints. Your rule becomes queryable immediately.

---

## Contributing

We especially welcome:

**Rule Contributions**:
- Document your successful optimization patterns
- Share what works for specific design types
- Help build the community rule library

**Diagnostic Patterns**:
- "When you see X symptom, try Y technique"
- Pattern recognition logic
- Automated bottleneck identification

**Tool Integration**:
- Support for other HLS tools
- Integration with other AI assistants
- Enhanced parsing for different report formats

**See CONTRIBUTING.md for guidelines.**

---

## Key Insights from Real Testing

### What We Learned Building FIR128

1. **Recording Results ≠ Reproducibility**
   - Saving "II=2" isn't enough
   - Need to save "HOW we got to II=2" (the rules)
   - This is why we focus on rule documentation

2. **AI Needs Knowledge Support**
   - Pure AI: Creative but inconsistent
   - AI + KB: Systematic and reproducible
   - Best results: AI applies your documented patterns

3. **Knowledge Compounds**
   - First FIR: Discover array partition (1 hour)
   - Second FIR: Apply array partition (15 minutes)
   - Tenth FIR: Start with all optimizations (5 minutes)

4. **You Build Your Own Expertise Library**
   - 287 general rules (foundation)
   - Your patterns (domain-specific)
   - Team knowledge (organizational asset)

**The system gets smarter as YOU use it.**

---

## License

MIT License - see LICENSE file.

## Thanks

Built by AICOFORGE team. Thanks to the HLS community for sharing knowledge.

**Let's make HLS optimization fast, predictable, and systematic!** 
