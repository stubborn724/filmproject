# 自动购票项目清理设计

## 目标

删除自动购票运行和维护不再需要的历史文档、缓存、旧上传目录及测试生成图片，同时保留可执行代码、配置、使用说明和自动测试。

## 删除范围

- 删除 `docs/` 下全部历史规格和实施计划，包括本清理规格。
- 删除项目内所有 `__pycache__/` 目录和 `.pyc` 文件。
- 删除根目录 `uploads/` 及其内容。
- 删除 `picture/` 中已有的 SVG 测试产物。

## 保留范围

- `movie_ticket_cli.py`。
- `config.local.json` 和 `config.example.json`。
- `backend/app/direct_ticketing.py` 及必要的包初始化文件。
- 根目录和 `backend/tests/` 下的全部自动测试。
- `README.md`、`requirements.txt` 和 `.gitignore`。

`picture/` 无需作为空目录提交；程序会在出票成功时自动创建配置指定的输出目录。

## 验证

- 运行完整 `unittest` 测试套件，预期 29 项通过。
- 运行真实 `--check-only`，只允许出现查询场次、查询座位图、查询座位状态和本地构造锁座参数，不允许出现锁座或支付步骤。
- 确认 Git 工作树中不再存在 `docs/`、`uploads/`、缓存文件或旧 SVG。
- 确认被忽略的 `config.local.json` 仍存在且未进入 Git。
