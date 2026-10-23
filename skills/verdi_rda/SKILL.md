---
name: verdi_rda
description: >
  Verdi RDA (Regression Debug Automation) 深度技能: Auto Binning /
  Transaction Diff / Message Analysis / DUT RCA / TB RCA / X RCA /
  MCPRCA / Debug Facilitator。504 结构化单元向量检索。
  RDA UG 9,874 行 / 324KB 深度知识。
version: 2.0.0
---
# Verdi RDA — Regression Debug Automation (深度版)

## When To Use
- 回归失败后自动分箱 (Auto Binning) 失败用例
- Transaction Diff: 参考与目标仿真 transaction 逐一比对
- Message Analysis: UVM_ERROR → transaction/signal 自动关联
- DUT RCA: RTL 内部信号根因定位
- TB RCA: Driver/Monitor/Sequence 根因定位
- X RCA: X 值传播源追踪
- MCPRCA: 多周期路径根因
- Debug Facilitator: 自动 rebuild/re-run

## RDA 九模块架构
```
Regression Results
       │
       ▼
┌── Auto Binning ──────────────────────────────┐
│  按 failure signature 自动聚类               │
│  相同根因的用例归入同一 bin                    │
├── Transaction Diff (TBRCA) ──────────────────┤
│  比对 reference vs target FSDB               │
│  定位首个 divergent transaction               │
├── Message Analysis (TBRCA) ──────────────────┤
│  UVM_ERROR 消息分析                           │
│  自动关联 transaction + signal                │
├── DUT RCA ──────────────────────────────────┤
│  RTL 内部信号逐周期比对                       │
│  定位首个 divergent cycle + signal            │
├── TB RCA ───────────────────────────────────┤
│  Driver/Monitor/Sequence 差异分析             │
│  定位 testbench 组件根因                      │
├── X RCA ────────────────────────────────────┤
│  X 值传播路径追踪                             │
│  定位 X source → X sink                       │
├── MCPRCA ───────────────────────────────────┤
│  多周期路径约束冲突分析                       │
├── Debug Facilitator ────────────────────────┤
│  自动 rebuild 失败用例                        │
│  自动 re-run + 采集 waveform                  │
└──────────────────────────────────────────────┘
```

## Data Assets
| 资源 | 路径 |
|---|---|
| RDA UG 结构化单元 | `corpus/verdi_rda/rda_units.jsonl` (680 units) |
| RDA UG 向量索引 | `corpus/verdi_rda/rda_vectors.npz` |
| RDA UG 原始文本 | `$VERDI_HOME/doc/.verdi_rda_ug.txt.gz` (9,874 lines) |
| RDA Demo (Txn) | `$VERDI_HOME/demo/RDA/TBRCA/transaction_analysis_example.tar.gz` |
| RDA Demo (Msg) | `$VERDI_HOME/demo/RDA/TBRCA/message_analysis_example.tar.gz` |
| RDA UG HTML | `$VERDI_HOME/doc/HTML/verdi_rda_ug/` |

## VCS Compile Flags for RDA
```bash
vcs -sverilog -timescale=1ns/1ns \
    +define+UVM_VERDI_PORT_RECORDING \
    -lca -kdb \
    -debug_access+all+reverse \
    +vpi \
    -ntb_opts uvm-1.1 \
    -full64 \
    +incdir+<env_dir> \
    <tb_top>.sv -l comp.log
```

## RDA Analysis Commands
```bash
# Transaction Diff / Message Analysis
autorca -cfg tbrca.yaml

# Debug Facilitator (without EMAN)
autorca_df.sh

# Coverage report (ICO)
crg -dir shared_record -report rpt_name -format both
```

## RDA Config (tbrca.yaml)
```yaml
usage_mode: tbrca
tbrca:
  target_waveform: target_data/novas.fsdb
  target_simv_daidir: target_data/simv.daidir/
  target_sim_log: target_data/simv.log
  reference_waveform: reference_data/novas.fsdb
  reference_simv_daidir: reference_data/simv.daidir/
```

## MCP Integration
| 操作 | MCP 工具 |
|---|---|
| Log 分析 | `chip_analyze_eda_log` |
| 波形查看 | `chip_open_waveform` |
| RAG 检索 | `chip_rag_search("RDA...")` |
| UG 检索 | `chip_ug_search("RDA...", product="verdi")` |

## Pitfalls
- RDA 编译必须加 `-kdb` + `-debug_access+all+reverse`
- FSDB 必须有 `UVM_VERDI_PORT_RECORDING` 才有 transaction 数据
- Reference 和 Target 必须使用相同 TB 结构
- `autorca` 需要 `tbrca.yaml` 中 FSDB 路径正确
- X RCA 需要 `-debug_access+all` 追踪 X 传播
- Message Analysis 需要 UVM reporting (不能用 $display)
- RDA license: VERDI_APEX_AN feature
