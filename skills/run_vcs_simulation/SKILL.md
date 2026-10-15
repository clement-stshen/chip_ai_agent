---
name: run_vcs_simulation
description: VCS 编译+仿真 (Synopsys verif-agent-mcp 远程工具): tb_top/test_name/seed/enable_cov/timeout_s -> pass/fail/timeout + UVM_FATAL/ERROR 列表 + log_path
target: [verification]
---
# run_vcs_simulation (Synopsys verif-agent-mcp)

## When To Use
- 意图匹配 "run vcs simulation" / verif_agent_flow recipe 步骤
- 经 MCP adapter 调用外部 server: `/opt/verif-agent-mcp/venv/bin/verif-agent-mcp`
  (VERIF_AGENT_TRANSPORT=stdio VERIF_AGENT_BACKEND=stub|production)

## Method
1. chip_edatools 查看 verif_agent_mcp 安装状态与启动命令
2. mcp_adapter 配置该 server 命令后, agent.run 自动路由本技能到外部 tools/call
3. production 后端需配置 vrf_script/ipvgen_script (/etc/verif-agent-mcp/config.yaml)

## Pitfalls
- stub 后端返回确定性假结果, 仅用于链路验证; 真实 EDA 需 production + 脚本路径
- 外部 server 未配置时本技能步骤报 "no MCP server configured" (预期降级)
