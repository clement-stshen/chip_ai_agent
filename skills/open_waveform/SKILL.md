---
name: open_waveform
description: 在 Verdi 中打开 FSDB 波形 (构造 -ssf/-s 命令, 缺失时给 ready_command)
---
# Open Waveform (Verdi)

## When To Use
- 仿真后需要人工/Agent 查看波形取证

## Method
1. 命令: verdi -nologo -ssf <fsdb> [-s <signal>]...
2. 本机缺失时返回完整可复制命令 + module load 指引
3. 程序化波形读取走 pynpi (eda_tools.fsdb_inspect), 需真 VERDI_HOME

## Pitfalls
- GUI 工具不适合 Agent 直接解析, 取值/找X用 fsdb_inspect 程序化路径
