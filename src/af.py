#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ai-flavor 统一入口

按等级与属性分派到不同脚本：

  af.py scan    三轴×三层扫描（可按轴／层／文体／置信度调用不同规则集）
  af.py metrics 量化画像（密度、句长分布、语气词等基线与 z 值）
  af.py check   改稿对账（信息、模态、术语、节拍、篇幅、结构）
  af.py lexicon 词库合并与校验（raw/*.tsv → lexicon.tsv）

用法示例：
  python3 af.py scan 稿.md
  python3 af.py scan --level 修辞 稿.md          # 只查修辞层
  python3 af.py scan --axis 甲 --min-conf high 稿.md
  python3 af.py scan --register R1 --baseline b1.md b2.md -- 稿.md
  python3 af.py metrics 稿.md
  python3 af.py check 原稿.md 改稿.md
  python3 af.py lexicon            # 合并 raw/ 下全部词库
  python3 af.py lexicon --check    # 只校验不写
"""
import sys, os, importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

USAGE = __doc__


def run_merge():
    p = os.path.normpath(os.path.join(HERE, "..", "assets", "lexicon", "merge_lexicon.py"))
    spec = importlib.util.spec_from_file_location("merge_lexicon", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.main()


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        print(USAGE)
        return
    sub, rest = sys.argv[1], sys.argv[2:]
    sys.argv = [sub] + rest
    if sub == "scan":
        import af_scan
        af_scan.main()
    elif sub == "metrics":
        import af_metrics
        af_metrics.main()
    elif sub == "check":
        import af_check
        af_check.main()
    elif sub == "lexicon":
        run_merge()
    else:
        print(f"未知子命令：{sub}\n")
        print(USAGE)
        sys.exit(1)


if __name__ == "__main__":
    main()
