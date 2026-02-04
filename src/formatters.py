# -*- coding: utf-8 -*-
"""
===================================
格式化工具組件
===================================

提供各種內容格式化工具組件函數，用於將通用格式轉換為平台特定格式。
"""

import re
import time
from typing import List, Callable


def format_feishu_markdown(content: str) -> str:
    """
    將通用 Markdown 轉換為飛書 lark_md 更友好的格式
    
    轉換規則：
    - 飛書不支援 Markdown 標題（# / ## / ###），用加粗代替
    - 引用塊使用前綴替代
    - 分隔線統一為細線
    - 表格轉換為條目列表
    
    Args:
        content: 原始 Markdown 內容
        
    Returns:
        轉換後的飛書 Markdown 格式內容
        
    Example:
        >>> markdown = "# 標題\\n> 引用\\n| 列1 | 列2 |"
        >>> formatted = format_feishu_markdown(markdown)
        >>> print(formatted)
        **標題**
        💬 引用
        • 列1：值1 | 列2：值2
    """
    def _flush_table_rows(buffer: List[str], output: List[str]) -> None:
        """將表格緩衝區中的行轉換為飛書格式"""
        if not buffer:
            return

        def _parse_row(row: str) -> List[str]:
            """解析表格行，提取單元格"""
            cells = [c.strip() for c in row.strip().strip('|').split('|')]
            return [c for c in cells if c]

        rows = []
        for raw in buffer:
            # 跳過分隔行（如 |---|---|）
            if re.match(r'^\s*\|?\s*[:-]+\s*(\|\s*[:-]+\s*)+\|?\s*$', raw):
                continue
            parsed = _parse_row(raw)
            if parsed:
                rows.append(parsed)

        if not rows:
            return

        header = rows[0]
        data_rows = rows[1:] if len(rows) > 1 else []
        for row in data_rows:
            pairs = []
            for idx, cell in enumerate(row):
                key = header[idx] if idx < len(header) else f"列{idx + 1}"
                pairs.append(f"{key}：{cell}")
            output.append(f"• {' | '.join(pairs)}")

    lines = []
    table_buffer: List[str] = []

    for raw_line in content.splitlines():
        line = raw_line.rstrip()

        # 處理表格行
        if line.strip().startswith('|'):
            table_buffer.append(line)
            continue

        # 刷新表格緩衝區
        if table_buffer:
            _flush_table_rows(table_buffer, lines)
            table_buffer = []

        # 轉換標題（# ## ### 等）
        if re.match(r'^#{1,6}\s+', line):
            title = re.sub(r'^#{1,6}\s+', '', line).strip()
            line = f"**{title}**" if title else ""
        # 轉換引用塊
        elif line.startswith('> '):
            quote = line[2:].strip()
            line = f"💬 {quote}" if quote else ""
        # 轉換分隔線
        elif line.strip() == '---':
            line = '────────'
        # 轉換列表項
        elif line.startswith('- '):
            line = f"• {line[2:].strip()}"

        lines.append(line)

    # 處理末尾的表格
    if table_buffer:
        _flush_table_rows(table_buffer, lines)

    return "\n".join(lines).strip()


def _chunk_by_lines(content: str, max_bytes: int, send_func: Callable[[str], bool]) -> bool:
    """
    強制按行分割發送（無法智能分割時的 fallback）
    
    Args:
        content: 完整消息內容
        max_bytes: 單條消息最大位元組數
        send_func: 發送單條消息的函數
        
    Returns:
        是否全部發送成功
    """
    chunks = []
    current_chunk = ""
    
    # 按行分割，確保不會在多位元組字元中間截斷
    lines = content.split('\n')
    
    for line in lines:
        test_chunk = current_chunk + ('\n' if current_chunk else '') + line
        if len(test_chunk.encode('utf-8')) > max_bytes - 100:  # 預留空間給分頁標記
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = line
        else:
            current_chunk = test_chunk
    
    if current_chunk:
        chunks.append(current_chunk)
    
    total_chunks = len(chunks)
    success_count = 0
    
    for i, chunk in enumerate(chunks):
        # 添加分頁標記
        page_marker = f"\n\n📄 ({i+1}/{total_chunks})" if total_chunks > 1 else ""
        
        try:
            if send_func(chunk + page_marker):
                success_count += 1
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"飛書第 {i+1}/{total_chunks} 批發送異常: {e}")
        
        # 批次間隔，避免觸發頻率限制
        if i < total_chunks - 1:
            time.sleep(1)
    
    return success_count == total_chunks


def chunk_feishu_content(content: str, max_bytes: int, send_func: Callable[[str], bool]) -> bool:
    """
    將超長內容分段發送到飛書
    
    智慧分割策略：
    1. 優先按 "---" 分隔（股票之間的分隔線）
    2. 其次按 "### " 標題分割（每隻股票的標題）
    3. 最後按行強制分割
    
    Args:
        content: 完整消息內容
        max_bytes: 單條消息最大位元組數
        send_func: 發送單條消息的函數，接收內容字串，返回是否成功
        
    Returns:
        是否全部發送成功
    """
    def get_bytes(s: str) -> int:
        """獲取字串的 UTF-8 位元組數"""
        return len(s.encode('utf-8'))
    
    def _truncate_to_bytes(text: str, max_bytes: int) -> str:
        """按位元組截斷文本，確保不會在多位元組字元中間截斷"""
        encoded = text.encode('utf-8')
        if len(encoded) <= max_bytes:
            return text
        
        # 從最大位元組數開始向前查找，找到完整的 UTF-8 字元邊界
        truncated = encoded[:max_bytes]
        while truncated and (truncated[-1] & 0xC0) == 0x80:
            truncated = truncated[:-1]
        
        return truncated.decode('utf-8', errors='ignore')
    
    # 智慧分割：優先按 "---" 分隔（股票之間的分隔線）
    # 如果沒有分隔線，按 "### " 標題分割（每隻股票的標題）
    if "\n---\n" in content:
        sections = content.split("\n---\n")
        separator = "\n---\n"
    elif "\n### " in content:
        # 按 ### 分割，但保留 ### 前綴
        parts = content.split("\n### ")
        sections = [parts[0]] + [f"### {p}" for p in parts[1:]]
        separator = "\n"
    else:
        # 無法智慧分割，按行強制分割
        return _chunk_by_lines(content, max_bytes, send_func)
    
    chunks = []
    current_chunk = []
    current_bytes = 0
    separator_bytes = get_bytes(separator)
    
    for section in sections:
        section_bytes = get_bytes(section) + separator_bytes
        
        # 如果單個 section 就超長，需要強制截斷
        if section_bytes > max_bytes:
            # 先發送當前積累的內容
            if current_chunk:
                chunks.append(separator.join(current_chunk))
                current_chunk = []
                current_bytes = 0
            
            # 強制截斷這個超長 section（按位元組截斷）
            truncated = _truncate_to_bytes(section, max_bytes - 200)
            truncated += "\n\n...(本段內容過長已截斷)"
            chunks.append(truncated)
            continue
        
        # 檢查加入後是否超長
        if current_bytes + section_bytes > max_bytes:
            # 保存當前塊，開始新塊
            if current_chunk:
                chunks.append(separator.join(current_chunk))
            current_chunk = [section]
            current_bytes = section_bytes
        else:
            current_chunk.append(section)
            current_bytes += section_bytes
    
    # 添加最後一塊
    if current_chunk:
        chunks.append(separator.join(current_chunk))
    
    # 分批發送
    total_chunks = len(chunks)
    success_count = 0
    
    for i, chunk in enumerate(chunks):
        # 添加分頁標記
        if total_chunks > 1:
            page_marker = f"\n\n📄 ({i+1}/{total_chunks})"
            chunk_with_marker = chunk + page_marker
        else:
            chunk_with_marker = chunk
        
        try:
            if send_func(chunk_with_marker):
                success_count += 1
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"飛書第 {i+1}/{total_chunks} 批發送異常: {e}")
        
        # 批次間隔，避免觸發頻率限制
        if i < total_chunks - 1:
            time.sleep(1)
    
    return success_count == total_chunks
