#!/usr/bin/env python3
"""统一测试入口脚本 - 支持 unittest 和 pytest 两种运行方式"""

import argparse
import os
import sys
import unittest
from pathlib import Path

def run_unittest_tests(test_pattern: str = "test_*.py", verbose: bool = True) -> None:
    """使用 unittest 运行测试"""
    # 添加 src 到 Python 路径
    src_root = Path(__file__).parent / "src"
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))
    
    # 发现测试
    test_loader = unittest.TestLoader()
    test_dir = Path(__file__).parent / "tests"
    
    if test_pattern == "test_*.py":
        # 运行所有测试
        suite = test_loader.discover(str(test_dir), pattern=test_pattern)
    else:
        # 运行特定测试文件
        specific_test = test_dir / test_pattern
        if specific_test.exists():
            suite = test_loader.discover(str(test_dir), pattern=test_pattern)
        else:
            print(f"测试文件不存在: {specific_test}")
            return
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2 if verbose else 1)
    result = runner.run(suite)
    
    # 返回适当的退出码
    sys.exit(0 if result.wasSuccessful() else 1)

def run_pytest_tests(test_pattern: str = "test_*.py", verbose: bool = True) -> None:
    """使用 pytest 运行测试（如果可用）"""
    try:
        import pytest
    except ImportError:
        print("pytest 未安装，将使用 unittest 运行测试")
        run_unittest_tests(test_pattern, verbose)
        return
    
    # 构建 pytest 参数
    args = []
    if verbose:
        args.append("-v")
    
    # 设置测试路径
    test_dir = Path(__file__).parent / "tests"
    if test_pattern == "test_*.py":
        args.append(str(test_dir))
    else:
        specific_test = test_dir / test_pattern
        if specific_test.exists():
            args.append(str(specific_test))
        else:
            print(f"测试文件不存在: {specific_test}")
            return
    
    # 运行 pytest
    exit_code = pytest.main(args)
    sys.exit(exit_code)

def main():
    parser = argparse.ArgumentParser(description="OpenClaw WebChat Adapter 测试运行器")
    parser.add_argument(
        "--runner", 
        choices=["unittest", "pytest"], 
        default="unittest",
        help="选择测试运行器 (默认: unittest)"
    )
    parser.add_argument(
        "--pattern", 
        default="test_*.py",
        help="测试文件匹配模式 (默认: test_*.py)"
    )
    parser.add_argument(
        "--quiet", 
        action="store_true",
        help="安静模式，减少输出"
    )
    
    args = parser.parse_args()
    
    print(f"使用 {args.runner} 运行测试...")
    print(f"测试模式: {args.pattern}")
    
    if args.runner == "pytest":
        run_pytest_tests(args.pattern, not args.quiet)
    else:
        run_unittest_tests(args.pattern, not args.quiet)

if __name__ == "__main__":
    main()