纯标准库示例，无需第三方数值依赖。
在支撑包根目录执行：
python code/solve.py --out results/solution.json
python -m unittest discover -s code -p "test_*.py"
结果为 slope=2, intercept=1, sse=0。仅验证这个合成算例。
