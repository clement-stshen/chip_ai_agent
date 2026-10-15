---
name: waveform_causal_diagnosis
description: DVCon 2025 因果诊断: 从现象时刻沿驱动链/事件链回溯根因, 而非只报现象
---
# Waveform Causal Diagnosis

## When To Use
- 已知故障现象 (总线挂死/X 值/时延超标), 需要根因时

## Method (DVCon 2025)
1. 现象时刻 T0 → 首次异常时刻 T-1 (X/跳变/握手断裂)
2. 沿驱动链回溯到源端 RTL 赋值, 形成 T-1..T0 因果链
3. 交叉验证: 静态连通性 (static_connectivity) 与动态驱动链一致才算确认
4. 输出格式固定: 现象 → 首次异常 → 驱动链 → 根因代码行 → 建议

## Steps
  1. detect_unknown_and_get_previous_or_next_transitions / signal_event_report 找 T-1
  2. trace_chain_driver_workflow 展开驱动链
  3. get_source_code 定位根因行
  4. static_connectivity_trace 交叉验证

## Pitfalls
- 驱动链与静态连通性矛盾时, 优先怀疑时钟/复位域差异, 输出矛盾点而非二选一
