# 自动购票项目清理设计

## 目标

将购票核心迁移到项目根目录，删除整个 `backend/`，并清理历史文档、缓存、旧上传目录及测试生成图片，同时保留配置、使用说明和自动测试。

## 删除范围

- 删除 `docs/` 下全部历史规格和实施计划，包括本清理规格。
- 删除项目内所有 `__pycache__/` 目录和 `.pyc` 文件。
- 删除根目录 `uploads/` 及其内容。
- 删除 `picture/` 中已有的 SVG 测试产物。
- 删除整个 `backend/`，包括其中遗留的虚拟环境和包目录；迁移完成前先把仍需保留的核心代码与测试移出。

## 保留范围

- `movie_ticket_cli.py`。
- 根目录 `direct_ticketing.py`，内容来自原 `backend/app/direct_ticketing.py`。
- `config.local.json` 和 `config.example.json`。
- 根目录 `tests/` 下的全部自动测试；原 `backend/tests/test_direct_ticketing.py` 迁移为 `tests/test_direct_ticketing.py`。
- `README.md`、`requirements.txt` 和 `.gitignore`。

`picture/` 无需作为空目录提交；程序会在出票成功时自动创建配置指定的输出目录。

迁移后 `movie_ticket_cli.py` 和测试直接从根目录 `direct_ticketing` 导入。`direct_ticketing.py` 的项目根目录改为当前文件所在目录，避免默认图片路径因文件层级变化而指向项目外部。

## 验证

- 运行完整 `unittest` 测试套件，预期 29 项通过。
- 运行真实 `--check-only`，只允许出现查询场次、查询座位图、查询座位状态和本地构造锁座参数，不允许出现锁座或支付步骤。
- 确认 Git 工作树中不再存在 `backend/`、`docs/`、`uploads/`、缓存文件或旧 SVG。
- 确认被忽略的 `config.local.json` 仍存在且未进入 Git。
