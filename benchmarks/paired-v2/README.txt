改版＋旧提示词（paired-v2）

基于 30fd7b3528202987c7000f51dd62d7f6b6390b70，加上同一评测使用的工具协议修复。
worker.py 是原评测适配器；其中 SYSTEM 为旧提示词，prompt.txt 为其原文。普通 CLI 仍使用原项目提示词，不等于该评测配置。
worker.py 接收 JSON 配置路径，需提供 output、workspace、source_python、tokenizer、endpoint、variant、task、prompt；source_python 指向本仓库 python 目录，variant 为 modified。配套工具子进程使用 Linux Landlock/seccomp 隔离；不可通过关闭隔离伪称同一评测。benchmark.py 为原批量驱动，部署需另备隔离题目材料和本地模型服务。本目录不是一键下载题库/启动集群脚本。

模型 Qwen3-8B，vLLM 0.10.2，关闭 thinking，temperature=0，seed=20261109；上下文 16384、输出 2048；10 个实际工具轮次，Memory/MCP 关闭，只开放六种文件及 Shell 工具。原评测每题 Agent 570 秒，外层 600 秒，Shell 最多 60 秒，2 worker 共用服务。

2026-11-09 固定 Exercism Python 60 题：共同协议修复后的原版 18/60，改版 24/60。改版总 Token 1819552（原版 1535361），不能宣称节省 Token。改版 API 请求错误为 0。单次开发集结果，不代表泛化成绩。基础源码及修复与原运行一致；此次发布不重跑 GPU。
未加入后续新提示词、no_change/max_try 或按需历史 Memory 提案。
