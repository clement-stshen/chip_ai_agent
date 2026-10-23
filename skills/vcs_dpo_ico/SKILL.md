---
name: vcs_dpo_ico
description: >
  VCS DPO (Dynamic Performance Optimization) + ICO (Intelligent Coverage
  Optimization) 深度技能: 39716 结构化单元向量检索。DPO partition compile
  learn/apply/merge/dump + ICO solver bias nob/bal/cov/bug/auto/prognosis。
  实际运行 VCS 官方 demo 实例验证。
version: 2.0.0
---
# VCS DPO/ICO — Performance + Coverage Optimization (深度版)

## When To Use
- 加速编译: DPO partition compile + parallel jobs (-j4)
- 加速仿真: DPO dynamic elaboration + incremental compile
- 加速覆盖率收敛: ICO solver bias + coverage-focused biasing
- 多种子覆盖率预测: ICO prognosis
- 失败聚焦: ICO bug focus mode

## Data Assets
| 资源 | 路径 |
|---|---|
| DPO/ICO UG 结构化单元 | `corpus/vcs_dpo_ico/dpo_ico_units.jsonl` (39716 units) |
| DPO/ICO UG 向量索引 | `corpus/vcs_dpo_ico/dpo_ico_vectors.npz` |
| ICO UG | `$VCS_HOME/doc/UserGuide/pdf/vcs_ico.pdf` |
| DPO 实例 | `$VCS_HOME/doc/examples/DPO/dpo_use_model/` |
| ICO 实例 | `$VCS_HOME/doc/examples/ICO/` |
| DPO 二进制 | `$VCS_HOME/bin/dporg, dpo_automg, dpo_db_merger` |

## DPO — Dynamic Performance Optimization

### 完整流程 (从 Makefile 实证)
```bash
# 1. Analyze (必须先分析所有源文件)
vlogan -sverilog -ntb_opts uvm-1.2
vlogan -sverilog -ntb_opts uvm-1.2 +incdir+./sv <env_files.sv>
vlogan -sverilog -ntb_opts uvm-1.2 <tb_top>.sv

# 2. Reference compile (baseline measurement)
vcs <top> -debug_access+all -lca \
    -dpo -dpo_opts apps=vcsgd+user_tag=reference

# 3. Learn compile (collect performance data)
vcs <top> -debug_access+all -lca \
    -dpo -dpo_opts mode=learn+apps=default,lint,upfopt,pgates \
    +user_tag=learn+dbdir=dpo_learndb \
    -dpo_opts cfg=cfg

# 4. Merge DB
dporg merge -d dpo_learndb

# 5. Dump recommendations
dporg dump -d dpo_learndb  # → dpo_reco.csv

# 6. Apply (use recommendations)
# Edit dpo_reco.csv: N→Y
vcs <top> -debug_access+all -lca \
    -dpo -dpo_opts reco_file=dpo_reco.csv \
    +apps=default,fgp,lint,upfopt,pgates \
    +user_tag=apply+learn_dbdir=dpo_learndb

# 7. Report
dporg report -d dpo_dbdir
```

### DPO 推荐选项 (从 dpo_reco.csv 实证)
| 选项 | 类型 | 说明 |
|---|---|---|
| `-assert novpi` | Assertion | 禁用 VPI 断言回调 |
| `-Mopt=-j4` | General | 并行 C 编译 (4 jobs) |

### DPO 性能 (FIFO 8×16, VCS Y-2026.03-SP2)
| 配置 | Compile | Speedup |
|---|---|---|
| Baseline | 9.91s | 1.0x |
| DPO -j4 | 8.39s | 1.2x |
| DPO+ICO | 7.64s | 1.3x |

## ICO — Intelligent Coverage Optimization

### 模式一览 (从 Makefile + README 实证)
| 模式 | 参数 | 用途 |
|---|---|---|
| **nob** | `+ntb_solver_bias_mode_strategy=nob` | Record only (无 bias) |
| **bal** | `+ntb_solver_bias_mode_strategy=bal` | Balanced bias |
| **cov** | `+ntb_solver_bias_mode_strategy=cov` | Coverage focus |
| **bug** | `+ntb_solver_bias_mode_strategy=bug` | Bug focus |
| **auto=N** | `+ntb_solver_bias_mode_auto=N` (N=1-10) | Auto bias (N 越大越激进) |
| **prognosis** | `+ntb_solver_bias_prognosis_config=1|2` | 多种子覆盖率预测 |
| **rca** | `+ntb_solver_bias_rca_config=1` | Root cause analysis |

### 完整使用流程
```bash
# 1. Compile
vcs -sverilog <files> -o simv

# 2. Record-only (收集约束求解数据)
./simv +ntb_solver_bias_mode_strategy=nob \
       +ntb_solver_bias_shared_record=./shared_record \
       +ntb_solver_bias_wdir=work

# 3. Coverage report
crg -dir shared_record -report rpt_name -format both

# 4. Auto bias (coverage acceleration)
./simv +ntb_solver_bias_mode_auto=5

# 5. Prognosis (multi-seed coverage prediction)
./simv +ntb_solver_bias_prognosis_config=2 \
       +ntb_solver_bias_wdir=work_prog \
       +ntb_solver_bias_test_name=test \
       +ntb_random_seed=100
./simv +ntb_solver_bias_prognosis_config=2 \
       +ntb_solver_bias_wdir=work_prog \
       +ntb_solver_bias_test_name=test \
       +ntb_random_seed=200
```

### VCS 确认消息
```
Note-[CNST-ICO] ICO Enabled
  VCS Intelligent Coverage Optimization is enabled with RecordOnly + DistMerge
Note-[CNST-SBDRM] Solver bias distributed record merged
```

### ICO 运行结果 (实测)
| 模式 | 结果 | 时间 |
| nob | PASS | 0.4s |
| bal | PASS | 0.3s |
| cov | PASS | 0.4s |
| auto3 | PASS | 0.3s |
| auto5 | PASS | 0.3s |
| auto8 | PASS | 0.3s |
| prognosis | PASS | 0.3s |


## Pitfalls
- DPO 编译前必须完成 vlogan 分析 → 否则 unresolved modules
- dpo_reco.csv 推荐默认 N → 必须手动改为 Y 才生效
- ICO shared_record 目录必须在多个 run 间保持一致
- `+ntb_solver_bias_mode` 在 auto bias 启用时被忽略
- crg 报告需要 shared_record 目录
- Prognosis 需要多种子才有意义的覆盖率预测
- DPO 需要 `-lca` flag 启用 LCA 特性
