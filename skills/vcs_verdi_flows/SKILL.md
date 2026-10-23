---
name: vcs_verdi_flows
description: >
  VCS/Verdi 全部流程技能: X-propagation / ISR restart / fastcomp /
  error message control / save_restore / FGP profiling / nECO /
  FaultAnalysis / IDX debug acceleration。40+ 实例目录覆盖。
version: 1.0.0
---
# VCS/Verdi All Flows

## VCS Flows

### X-Propagation
```bash
# Compile with X-propagation
vcs test.v -sverilog -xprop=tmerge -debug_access+all
# Modes: tmerge (default), xmerge (more aggressive)
./simv +xprop_assert +xprop_verbose
```

### ISR (Interactive Simulation Restart)
```bash
# Record
vcs test.v -o simv1 -lca
./simv1 +ntb_solver_bias_isr=1 +ntb_solver_bias_isr_record=isr_record -lca
# Replay (faster, uses cached solver)
./simv1 +ntb_solver_bias_isr_replay=isr_record -lca
# Replay with cache
./simv1 +ntb_solver_bias_isr_replay=isr_record +ntb_solver_bias_isr_cache=1 -lca
# ISR + ICO
./simv1 +ntb_solver_bias_isr=1 +ntb_solver_bias_isr_record=isr_record +ntb_solver_bias_mode_auto=5 -lca
```

### fastcomp (Fast Elaboration)
```bash
vcs tb -fastcomp=il,mop -lca
# il = intermediate library, mop = module optimization
```

### Error Message Control
```bash
# Filter warnings by module
vcs test -debug_access+all -msg_config=warn_mod.config -sverilog
```

### Save/Restore
```bash
# Save checkpoint
./simv -save checkpoint.dat
# Restore from checkpoint
./simv -restore checkpoint.dat
```

### Fine-Grained Profiling (FGP)
```bash
vcs test -simprofile -simprofile_time -full64
./simv
# Report: profrpt -dir simprofile_dir
```

### simv -F (Runtime args from file)
```bash
./simv -f argv.f
```

## Verdi Flows

### nECO (Netlist ECO)
```bash
verdi -nologo -eco  # Requires KDB from VCS -kdb compile
```

### FaultAnalysis
```bash
verdi -nologo -fault  # Safety/fault analysis (ISO 26262)
```

### IDX (Intelligent Debug Acceleration)
```bash
verdi -nologo -ssf <fsdb>
# Sub-modes: IP_Debug, AIP_Debug, EIP_Debug, SVA_Debug, Waveform_Replay
# Requires -kdb compile for design database
```
