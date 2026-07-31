.PHONY: install dev test lint build run

install:        ## 安装(用户模式)
	pip install -e .

dev:            ## 安装开发依赖(测试/lint)
	pip install -e ".[dev]"

test:           ## 跑测试 + 覆盖率
	pytest

lint:           ## ruff + mypy
	ruff check llmdog.py tests/
	mypy llmdog.py || true

run:            ## 手动跑一次(DRY_RUN)
	python3 llmdog.py

build:          ## 打包 wheel/sdist
	pip install build && python -m build

timer-status:   ## 看 timer 状态
	systemctl --user status llmdog.timer --no-pager
	systemctl --user list-timers llmdog.timer --no-pager

logs:           ## 看日志
	tail -f logs/llmdog.log
