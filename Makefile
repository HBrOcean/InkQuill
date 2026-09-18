.PHONY: help run test lint fmt build clean selftest

help:
	@echo "InkQuill 常用命令："
	@echo "  make run IN=图片.png ARGS='--trim'   运行命令行转换"
	@echo "  make gui                             打开图形界面"
	@echo "  make test                            运行测试"
	@echo "  make lint                            代码检查"
	@echo "  make build                           打包当前平台可执行程序"
	@echo "  make selftest                        算法自检"
	@echo "  make clean                           清理构建产物"

run:
	python inkquill.py $(IN) $(ARGS)

gui:
	python inkquill.py

test:
	pytest -q

lint:
	ruff check .

fmt:
	ruff check --fix .

selftest:
	python inkquill.py --selftest

build:
	python build.py

clean:
	rm -rf build dist *.spec __pycache__ .pytest_cache .ruff_cache _selftest
