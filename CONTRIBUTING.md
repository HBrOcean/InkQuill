# 贡献指南

感谢你有兴趣让 InkQuill 变得更好！

## 开发环境

```bash
git clone https://github.com/HBrOcean/InkQuill.git
cd InkQuill
pip install -e ".[dev]"       # 安装依赖 + pytest + ruff
```

## 运行与测试

```bash
python inkquill.py                       # 图形界面
python inkquill.py 图片.png               # 命令行
python inkquill.py --selftest            # 算法自检（无界面）
python inkquill.py --gui-selftest        # 图形界面自检（Linux 无头环境需 xvfb-run）
pytest -q                                # 单元测试
ruff check .                             # 代码检查
```

## 提交 Pull Request

1. 从 `main` 切一个分支：`git checkout -b feature/your-idea`
2. 保持改动聚焦，尽量小步提交
3. 确保 `pytest -q` 与 `ruff check .` 通过
4. 在 `CHANGELOG.md` 的「未发布」处补一行说明
5. 提交 PR，描述清楚「做了什么 / 为什么」

## 代码风格

- 单文件主程序 `inkquill.py`，尽量不引入新依赖（当前依赖：opencv-python / numpy / pillow）
- 函数保持短小、带中文注释；核心算法放在「核心算法」区块
- 新增参数请同时更新：`Params`、CLI（argparse）、GUI 控件、README 参数表

## 报告问题

请用 Issue 模板，附上：
- 系统 / Python 版本
- 复现步骤
- 一张可公开的样例图（或描述图片特征）
- 实际输出 vs 期望输出
