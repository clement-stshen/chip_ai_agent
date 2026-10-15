---
name: run_simulation
description: 用 VCS 编译并运行 UVM 仿真, 解析 UVM 报告 (TEST PASSED/FAILED, error/fatal 计数)
---
# Run Simulation (VCS)

## When To Use
- 验证 testbench 生成/修改后需要实际仿真验证

## Method
1. 标准命令: vcs -full64 -sverilog +incdir+$UVM_HOME/src -f filelist.f
   && ./simv +UVM_TESTNAME=<test> +UVM_VERBOSITY=UVM_LOW
2. 解析 sim.log: ** TEST PASSED/FAILED **, UVM_ERROR/UVM_FATAL 计数
3. 失败时附 log 尾部 800 字符供根因分析
4. 工具缺失 → 返回 ready_command 在 EDA 主机执行, 不中断

## Pitfalls
- returncode==0 不等于通过, 必须看 UVM 报告
- 超时 (默认 600s) 视为失败, 需检查死锁/objection 未 drop
