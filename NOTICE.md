# 来源、授权与贡献边界

## 主代码与教程

- 来源：https://github.com/Windy3f3f3f3f/claude-code-from-scratch
- 固定基线：`0b452360866433fde0dc77cd37ada9d303546592`
- 许可证：MIT，根目录 LICENSE 保留原版权声明。
- 本仓库保留其 Git 历史、教程、TypeScript 与 Python 代码。README-UPSTREAM.md 是改写首页前的原始 README，目录位置不变，保留其相对链接。
- 根 README 与 docs/demo 是本分支文档；Python 可靠性改造、评估脚本、测试与报告是本分支新增/修改部分。
- 上游关于功能数量、双语言一致性、性能等描述属于上游版本说明，不作为本分支新验证结论。

## 方法参考

https://github.com/shareAI-lab/learn-claude-code

参考其 Agent 循环、上下文压缩及工作流日志/恢复的教学组织，特别是 s16_workflow_runtime。这里提供来源链接和本项目的技术对照，没有导入第二套运行框架，也没有将该项目全部教程复制进来。

## 声明

本项目用于学习与小型工程演示，与 Anthropic 无关联，不了解或声称复现 Claude Code 的私有内部实现。Qwen3-8B 权重、第三方依赖的授权由各自提供方决定，不包含在本仓库 MIT 许可范围内。
