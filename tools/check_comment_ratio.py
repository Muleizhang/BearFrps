#!/usr/bin/env python3
"""@file tools/check_comment_ratio.py
@brief 统计根项目源码的非空行和有效注释行，验证注释量是否不低于20%。
@author BearFrps课程设计小组
@course 武汉大学开源软件与技术课程 2026
@date 2026-06-10
@version 1.0
@copyright Apache-2.0
@details
  依赖关系：Python 标准库 pathlib、sys。
  修改记录：2026-06-10，新增课程设计注释覆盖率检查工具。
  本脚本用于课程提交前的本地自查。
  检查范围只包含 BearFrps 根项目源码。
  第三方目录 frp-Android 不参与根项目注释比例。
  二进制文件和缓存文件不参与统计。
  Python 文档字符串视为有效注释。
  HTML 注释块视为有效注释。
  JS/CSS/Go 块注释和行注释视为有效注释。
  Shell/PowerShell 的 # 注释视为有效注释。
  统计结果低于 20% 时返回非零退出码。
  输出低注释文件列表用于后续维护，不作为单文件强制门禁。

统计边界：
  非空行作为分母，空行不计入源码有效行。
  单行注释作为一行有效注释。
  多行块注释中的每个非空注释行都计入。
  Python 三引号文档字符串用于文件头、类说明和函数说明。
  该口径与课程“有效注释量”要求保持一致，便于复核。

输出说明：
  第一行输出全项目注释比例。
  第二行输出课程最低要求。
  低于 10% 的文件会被列入维护建议。
  达标时输出 passed 并返回 0。
  未达标时输出 failed 并返回 1。

维护说明：
  新增大文件后应先运行本脚本。
  低比例文件优先补文件头和接口注释。
  不建议用无意义注释刷比例。
  注释应解释约束、原因和副作用。
  修改代码时同步修改相邻注释。
  检查通过后再提交课程材料。
@section ratio_doxygen Doxygen 注释检查说明
  本工具接受 Doxygen 风格文件头。
  @file 行计入有效注释。
  @brief 行计入有效注释。
  @author 行计入有效注释。
  @course 行计入有效注释。
  @details 行计入有效注释。
  多行 @section 说明计入有效注释。
  Python docstring 适合承载 Doxygen 标记。
  HTML、CSS、JS 使用块注释承载 Doxygen 标记。
  Shell 使用 ## 和 # 承载 Doxygen 标记。
@section ratio_submission 平时作业检查说明
  注释比例低于 20% 时返回失败。
  失败输出用于定位需要补充说明的文件。
  通过输出可写入全局完整文档。
  本工具不替代人工代码审查。
  新增源码文件后应立即运行本工具。
  删除文档或注释后应重新运行本工具。
  函数注释应优先说明参数和返回值。
  模块注释应优先说明依赖和副作用。
  课程提交前必须保留通过记录。
  口头报告可展示本工具输出。
  全局文档应记录本工具结果。
  许可证文件不计入源码比例。
"""

from __future__ import annotations

from pathlib import Path
import sys


ROOT_DIR = Path(__file__).resolve().parents[1]
SOURCE_ROOTS = ("backend", "frontend", "scripts", "demo-server", "tests", "tools")
SOURCE_EXTENSIONS = {
    ".py",
    ".js",
    ".html",
    ".css",
    ".sh",
    ".ps1",
    ".go",
    ".tmpl",
}
MIN_COMMENT_RATIO = 0.20


def iter_source_files() -> list[Path]:
    """Return root-project source files that participate in comment auditing.

    返回值：按路径排序的源码文件列表。
    副作用：无。
    异常：无，缺失目录会被自然跳过。
    """

    files: list[Path] = []
    for root_name in SOURCE_ROOTS:
        root = ROOT_DIR / root_name
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix in SOURCE_EXTENSIONS:
                files.append(path)
    return sorted(files)


def count_file(path: Path) -> tuple[int, int]:
    """Count non-empty and comment lines for one source file.

    参数：path 为待统计文件的绝对路径。
    返回值：二元组 `(non_empty_lines, comment_lines)`。
    副作用：只读取文件，不修改源码。
    """

    text = path.read_text(encoding="utf-8", errors="ignore")
    suffix = path.suffix
    if suffix == ".py":
        return count_hash_and_docstring_comments(text)
    if suffix in {".js", ".css", ".go"}:
        return count_slash_comments(text)
    if suffix == ".html":
        return count_html_comments(text)
    if suffix in {".sh", ".ps1", ".tmpl"}:
        return count_hash_comments(text)
    return count_hash_comments(text)


def count_hash_comments(text: str) -> tuple[int, int]:
    """Count line comments for shell-like languages."""

    non_empty = 0
    comments = 0
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        non_empty += 1
        if stripped.startswith("#"):
            comments += 1
    return non_empty, comments


def count_hash_and_docstring_comments(text: str) -> tuple[int, int]:
    """Count Python `#` comments and triple-quoted documentation strings.

    课程注释规范允许文件、模块、类和函数使用文档字符串表达接口说明，
    因此这里把三引号文档行计入有效注释。
    """

    non_empty = 0
    comments = 0
    in_docstring = False
    doc_delimiter = ""
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        non_empty += 1

        if in_docstring:
            comments += 1
            if doc_delimiter in stripped:
                in_docstring = False
            continue

        if stripped.startswith("#"):
            comments += 1
            continue

        for delimiter in ('"""', "'''"):
            if stripped.startswith(delimiter):
                comments += 1
                if stripped.count(delimiter) < 2:
                    in_docstring = True
                    doc_delimiter = delimiter
                break
    return non_empty, comments


def count_slash_comments(text: str) -> tuple[int, int]:
    """Count `//` and `/* */` comments for JS, CSS, and Go files."""

    non_empty = 0
    comments = 0
    in_block = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        non_empty += 1

        if in_block:
            comments += 1
            if "*/" in stripped:
                in_block = False
            continue

        if stripped.startswith("//"):
            comments += 1
            continue
        if stripped.startswith("/*"):
            comments += 1
            if "*/" not in stripped:
                in_block = True
    return non_empty, comments


def count_html_comments(text: str) -> tuple[int, int]:
    """Count HTML comment blocks while treating embedded JS/CSS as source."""

    non_empty = 0
    comments = 0
    in_html_comment = False
    in_slash_block = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        non_empty += 1

        if in_html_comment:
            comments += 1
            if "-->" in stripped:
                in_html_comment = False
            continue
        if in_slash_block:
            comments += 1
            if "*/" in stripped:
                in_slash_block = False
            continue

        if stripped.startswith("<!--"):
            comments += 1
            if "-->" not in stripped:
                in_html_comment = True
            continue
        if stripped.startswith("//"):
            comments += 1
            continue
        if stripped.startswith("/*"):
            comments += 1
            if "*/" not in stripped:
                in_slash_block = True
    return non_empty, comments


def main() -> int:
    """Run the audit and return a process exit code."""

    total_non_empty = 0
    total_comments = 0
    file_rows: list[tuple[str, int, int, float]] = []

    for path in iter_source_files():
        non_empty, comments = count_file(path)
        total_non_empty += non_empty
        total_comments += comments
        ratio = comments / non_empty if non_empty else 1.0
        file_rows.append((str(path.relative_to(ROOT_DIR)), non_empty, comments, ratio))

    ratio = total_comments / total_non_empty if total_non_empty else 1.0
    print(f"Comment ratio: {ratio:.2%} ({total_comments}/{total_non_empty})")
    print(f"Required minimum: {MIN_COMMENT_RATIO:.0%}")

    low_files = [row for row in file_rows if row[1] >= 20 and row[3] < 0.10]
    if low_files:
        print("\nFiles below 10% comments, review when adding future code:")
        for name, non_empty, comments, file_ratio in low_files[:20]:
            print(f"  {file_ratio:.2%} {comments}/{non_empty} {name}")

    if ratio < MIN_COMMENT_RATIO:
        print("\nComment ratio check failed.")
        return 1
    print("\nComment ratio check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
