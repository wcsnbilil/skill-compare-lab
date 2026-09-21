# Skills 实测对比台

把同一个 Python 修复任务分别交给“未注入 Skill”“Skill A”“Skill B”，重复运行，再用固定测试检查实际代码结果。报告能点开每一次试验，查看代码差异、测试输出和输入指令。

## 先运行演示

在项目根目录运行（Python 3.11+）：

```sh
python -m skill_compare_lab demo --output runs/demo
```

打开 `runs/demo/report.html`。这个演示不需要模型账号，真正运行了测试，但代码来自预设样例，**不能用演示数据判断 Skill 的效果**。

## 运行真实比较

安装并登录 Codex CLI，准备 Docker，然后运行：

```sh
python -m pip install .
docker pull python:3.12-slim
skill-compare run --skill examples/skills/contract-first --skill examples/skills/minimal-change --model YOUR_MODEL_ID --repeats 3 --output runs/comparison
```

把 `YOUR_MODEL_ID` 换成账号可用的模型 ID。默认是 3 个任务 × 3 个条件 × 3 次重复，即 27 次模型调用，会消耗模型用量。加 `--task chunks --repeats 1` 可先做 3 次调用的集成检查。

`--skill` 接受 SKILL.md 或所在目录，目录名称要不同。替换为自己的 Skill 即可比较。每次选择新的输出目录，已有结果不会被覆盖。

## 怎么读结果

- **Passed / attempted**：通过全部测试的次数 / 已尝试次数，超时和运行错误也会保留。
- **Paired wins / losses / ties**：同一任务、同一次重复与基线配对，只比较完成测试的有效结果。
- **Reported tokens**：CLI 报告的输入加输出；缓存输入单独展示，不能再重复加一次。缺失用量显示未知。
- 点开任务矩阵里的结果，查看代码修改、失败测试和原始 prompt。

首版仅评估 SKILL.md 文本注入后的指令效果，不评估原生 Skill 自动触发，也不运行 Skill 附带的脚本和素材。三个小任务上的表现不能代表所有工作场景。Codex 会继承本机设置和可能存在的全局指令，比较时应保持配置一致。

Docker 只隔离生成代码的评分过程；Codex 自身使用只读沙盒。`--executor local` 会直接在本机执行生成的 Python，仅适合可信、可丢弃的开发环境。报告内含 prompt 和代码，分享前检查是否包含私有内容。

完整方法、产物结构、已知限制及相关项目见[英文 README](../README.md)。
