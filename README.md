# Lab Generate Skill

从浏览器任务轨迹提取技能，经检索、Generator 候选、Actor 执行、Teacher 修订与独立复核，形成符合资格的训练目标。项目覆盖 Shopping Admin、Shopping、GitLab、Reddit 和 Map 的站点接口与判定。

本分支是独立的源码与文档发布，采用 **2026-11-11 已验共用代码快照**。软件检查、真实业务完成和训练验收分别判断；发布不表示五站全流程已通过。

- [项目代码阅读指南](docs/CODE-READING-GUIDE.zh-CN.md)：模块入口和调用跟踪。
- [AI 应用技术与面试备考手册](docs/AI-APPLICATION-TECHNICAL-HANDBOOK.zh-CN.md)：20 章实现、取舍、并发与面试准备。
- [框架模块职责](docs/FRAMEWORK_MODULES.md)与[架构合同](docs/design/codebase-architecture-v1.md)。
- [安装与检查](docs/DEVELOPMENT.md)：依赖、Slurm 检查及外部资产边界。
- [发布范围与版本](docs/EXPORT.md)：来源、排除项及验收范围。

```text
src/lab_generate_skill/   领域、端口、策略、编排、装配和五站适配
  domain/ ports/ policies/
  application/ bootstrap/
  adapters/ runtime/ sites/ task_families/ evaluators/
tests/                   测试及辅助 Python 源码
tools/                   工程检查和阶段提示脚本
cluster/                 原 workspace 的 Slurm 脚本参考
docs/                    阅读指南、手册、架构和开发约定
```

运行回执、实验日志、数据库、轨迹、任务数据、模型权重、Python 环境和私有部署配置不在本分支。依赖这些材料的集成测试须由原部署提供输入，不能用空数据冒充通过。普通阅读和公开单元检查见开发说明。
