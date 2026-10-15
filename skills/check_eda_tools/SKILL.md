---
name: check_eda_tools
description: 发现 VCS/Verdi/NPI 可用性: PATH + modulefile 声明 + 常见安装根, 缺失时给精确 setup
---
# Check EDA Tools (VCS / Verdi / NPI)

## When To Use
- 任何仿真/波形任务之前, 先确认工具环境

## Method
1. 按顺序发现: PATH → modulefile 声明的 VERDI_HOME/VCS_HOME → 常见安装根
2. 二进制不存在时返回: 声明路径 + `module load synopsys` 指引
3. NPI 套件单独检测 (pynpi 可 import, 波形 DB 需真 VERDI_HOME)

## Pitfalls
- modulefile 声明的路径在本机不存在 ≠ 工具未安装, 可能在 LSF 计算节点
- 分析机上工具缺失是常态, 必须降级返回可复制命令而非报错中断
