# -*- coding: utf-8 -*-
import os
import re
import chardet
from collections import deque
from constants import CHUNK_SIZE, LARGE_FILE_THRESHOLD, STREAMING_LINE_PROGRESS_INTERVAL
from file_reader import FileReader

# 尝试导入jsbeautifier，如果未安装则使用None
try:
    import jsbeautifier
    JS_BEAUTIFIER_AVAILABLE = True
except ImportError:
    JS_BEAUTIFIER_AVAILABLE = False
    jsbeautifier = None

class TextProcessor:
    """负责文本搜索的核心逻辑"""
    def __init__(self, config, auto_detect_encoding=True):
        self.config = config
        self.auto_detect_encoding = auto_detect_encoding
        self.encoding_cache = {}
        self.compiled_regex_cache = {}
        self.file_reader = FileReader(auto_detect_encoding)

    def get_compiled_pattern(self, pattern_str):
        """获取或编译正则表达式模式（带缓存）"""
        if pattern_str not in self.compiled_regex_cache:
            try:
                self.compiled_regex_cache[pattern_str] = re.compile(pattern_str)
            except re.error as e:
                print(f"正则表达式编译错误: {pattern_str} - {str(e)}")
                self.compiled_regex_cache[pattern_str] = None
        return self.compiled_regex_cache[pattern_str]
    
    def is_js_file(self, file_path):
        """检查文件是否为JavaScript文件"""
        if not file_path:
            return False
        file_ext = os.path.splitext(file_path)[1].lower()
        return file_ext in ['.js', '.jsx', '.mjs', '.cjs']
    
    def beautify_js(self, code_text):
        """美化JavaScript代码"""
        if not code_text or not code_text.strip():
            return code_text
        
        if not JS_BEAUTIFIER_AVAILABLE:
            # 如果没有安装jsbeautifier，返回原始文本
            return code_text
        
        try:
            # 配置美化选项
            opts = jsbeautifier.default_options()
            opts.indent_size = 2  # 缩进2个空格
            opts.preserve_newlines = True  # 保留换行
            opts.max_preserve_newlines = 2  # 最多保留2个连续换行
            opts.keep_array_indentation = False  # 不保持数组缩进
            opts.break_chained_methods = False  # 不断开链式调用
            opts.indent_scripts = 'normal'  # 正常缩进脚本
            opts.brace_style = 'collapse'  # 大括号风格
            opts.space_before_conditional = True  # 条件语句前加空格
            opts.unescape_strings = False  # 不转义字符串
            opts.wrap_line_length = 0  # 不限制行长度
            
            beautified = jsbeautifier.beautify(code_text, opts)
            return beautified
        except Exception as e:
            # 如果美化失败，返回原始文本
            print(f"JS美化失败: {str(e)}")
            return code_text

    @staticmethod
    def _build_char_snippets(line, matches, kw_chars):
        """根据匹配位置截取前后字符内容"""
        if not matches:
            return ""
        snippets = []
        seen = set()
        for match in matches:
            start = match.start()
            end = match.end()
            pre_start = max(0, start - kw_chars)
            post_end = min(len(line), end + kw_chars)
            snippet = f"{line[pre_start:start]}[{match.group()}]{line[end:post_end]}"
            if snippet not in seen:
                seen.add(snippet)
                snippets.append(snippet)
        return "\n".join(snippets)
    
    @staticmethod
    def _get_raw_nearby_chars_text(line, matches, kw_chars):
        """获取原始附近字符文本（用于排除检查，不包含格式化标记）"""
        if not matches or kw_chars <= 0:
            return ""
        raw_texts = []
        seen = set()
        for match in matches:
            start = match.start()
            end = match.end()
            pre_start = max(0, start - kw_chars)
            post_end = min(len(line), end + kw_chars)
            raw_text = line[pre_start:post_end]
            if raw_text not in seen:
                seen.add(raw_text)
                raw_texts.append(raw_text)
        return "\n".join(raw_texts)

    def detect_encoding(self, file_path):
        """检测文件编码（委托给 FileReader）"""
        return self.file_reader.detect_encoding(file_path)

    def read_file_optimized(self, file_path):
        """读取文件（使用 FileReader 支持多种格式）"""
        return self.file_reader.read_file(file_path)
    
    def process_file_streaming(self, file_path, progress_callback=None):
        """
        流式处理大文件，逐行读取和处理，避免一次性加载整个文件到内存
        返回: (result_text, results)
        """
        # 使用流式处理方法
        try:
            # 检查文件大小和类型
            file_size = os.path.getsize(file_path)
            is_text_file = self.file_reader.is_text_file(file_path)
            is_large_file = file_size > LARGE_FILE_THRESHOLD
            
            # 对于大文本文件，优先使用流式处理
            # 对于小文件也可以使用流式处理（性能更好）
            if is_text_file:
                return self._process_text_file_streaming(file_path, progress_callback)
            else:
                # 特殊格式文件，使用原有方法
                content = self.read_file_optimized(file_path)
                if content is None:
                    return "", []
                return self.process_text(content, file_path)
        except Exception as e:
            print(f"流式处理文件 {file_path} 时出错: {str(e)}")
            # 回退到原有方法
            try:
                content = self.read_file_optimized(file_path)
                if content is None:
                    return "", []
                return self.process_text(content, file_path)
            except:
                return "", []
    
    def _process_text_file_streaming(self, file_path, progress_callback=None):
        """流式处理文本文件"""
        keywords = self.config["keywords"]
        default_nearby_lines = self.config["nearby_lines"]
        default_nearby_chars = self.config["nearby_chars"]
        
        is_js = self.is_js_file(file_path)
        results = []
        result_lines = []
        total_hits = 0
        
        # 检测编码
        if self.auto_detect_encoding:
            encoding = self.file_reader.detect_encoding(file_path)
        else:
            encoding = 'utf-8'

        # 预编译所有正则表达式和模式，避免重复编译
        compiled_keywords = []
        for kw_config in keywords:
            words = kw_config.get("words", [])
            if not words:
                continue
            
            use_regex = kw_config.get("use_regex", False)
            kw_chars_setting = kw_config.get("nearby_chars", default_nearby_chars)
            compiled_patterns = {}
            plain_patterns = []
            
            if use_regex:
                for word in words:
                    if word:
                        pattern = self.get_compiled_pattern(word)
                        compiled_patterns[word] = pattern
            else:
                # 对于普通文本，预编译第一个关键字用于字符截取
                first_word = words[0] if words else None
                if first_word and kw_chars_setting > 0:
                    plain_patterns.append(re.compile(r'(' + re.escape(first_word) + ')'))
            
            compiled_keywords.append({
                'config': kw_config,
                'words': words,
                'compiled_patterns': compiled_patterns,
                'plain_patterns': plain_patterns,
                'compiled_excludes': None
            })
        
        default_down_lines = self.config.get("down_lines", 0)
        default_up_lines = self.config.get("up_lines", 0)
        max_prev_lines = 0
        max_next_lines = 0
        for kw in keywords:
            kw_lines = kw.get("nearby_lines", default_nearby_lines)
            if kw_lines != -1:
                max_prev_lines = max(max_prev_lines, kw_lines)
                max_next_lines = max(max_next_lines, kw_lines)
            down_val = kw.get("down_lines", default_down_lines)
            up_val = kw.get("up_lines", default_up_lines)
            if down_val >= 0:
                max_next_lines = max(max_next_lines, down_val)
            else:
                max_prev_lines = max(max_prev_lines, abs(down_val))
            if up_val >= 0:
                max_prev_lines = max(max_prev_lines, up_val)
            else:
                max_next_lines = max(max_next_lines, abs(up_val))
        
        past_window = deque()
        future_window = deque()
        
        try:
            # 使用更大的缓冲区提升IO性能
            with open(file_path, 'r', encoding=encoding, errors='ignore', buffering=CHUNK_SIZE) as f:
                line_counter = 0
                
                def read_next_line():
                    nonlocal line_counter
                    raw_line = f.readline()
                    if not raw_line:
                        return None
                    line_counter += 1
                    return (line_counter, raw_line.rstrip('\n\r'))
                
                def refill_future_buffer():
                    if max_next_lines <= 0:
                        return
                    while len(future_window) < max_next_lines:
                        next_entry = read_next_line()
                        if not next_entry:
                            break
                        future_window.append(next_entry)
                
                current_entry = read_next_line()
                if current_entry is None:
                    return "", []
                
                refill_future_buffer()
                
                while current_entry:
                    line_no, line = current_entry
                    
                    # 定期报告进度（降低更新频率以减少UI开销）
                    if progress_callback and line_no % STREAMING_LINE_PROGRESS_INTERVAL == 0:
                        progress_callback(line_no)
                    
                    # 构建当前行的上下文窗口（包含前后文）
                    context_window = list(past_window) if past_window else []
                    context_window.append(current_entry)
                    if future_window:
                        context_window.extend(future_window)
                    
                    # 处理当前行（使用预编译的模式）
                    for kw_data in compiled_keywords:
                        kw_config = kw_data['config']
                        words = kw_data['words']
                        compiled_patterns = kw_data['compiled_patterns']
                        plain_patterns = kw_data['plain_patterns']
                        
                        exclude = kw_config.get("exclude", [])
                        kw_lines = kw_config.get("nearby_lines", default_nearby_lines)
                        kw_chars = kw_config.get("nearby_chars", default_nearby_chars)
                        down_lines = kw_config.get("down_lines", self.config.get("down_lines", 0))
                        up_lines = kw_config.get("up_lines", self.config.get("up_lines", 0))
                        exclude_nearby = kw_config.get("exclude_nearby", True)
                        multi_line_exclude = kw_config.get("multi_line_exclude", False)
                        use_regex = kw_config.get("use_regex", False)
                        remark = kw_config.get("remark", "").strip()
                        
                        # 检查匹配（使用预编译的模式）
                        match_success = self._check_line_match_optimized(
                            line, words, use_regex, multi_line_exclude, 
                            context_window, line_no, kw_lines, down_lines, up_lines,
                            compiled_patterns
                        )
                        
                        if not match_success:
                            continue
                        
                        # 获取上下文
                        nearby_lines_text = self._get_nearby_lines_from_window(
                            context_window, line_no, kw_lines
                        )
                        down_text = self._get_down_text_from_window(
                            context_window, line_no, down_lines
                        )
                        up_text = self._get_up_text_from_window(
                            context_window, line_no, up_lines
                        )
                        # 使用预编译的模式获取附近字符（用于显示）
                        matches_for_chars = []
                        if kw_chars > 0 and plain_patterns:
                            matches_for_chars = list(plain_patterns[0].finditer(line))
                            nearby_chars_text = self._build_char_snippets(line, matches_for_chars, kw_chars)
                        elif kw_chars > 0 and use_regex and words:
                            pattern = compiled_patterns.get(words[0])
                            if pattern:
                                matches_for_chars = list(pattern.finditer(line))
                                nearby_chars_text = self._build_char_snippets(line, matches_for_chars, kw_chars)
                            else:
                                nearby_chars_text = ""
                        else:
                            nearby_chars_text = ""
                        
                        # 检查排除：根据配置分别检查不同区域，并记录命中的排除文本
                        excluded = False
                        hit_exclude_text = ""
                        exclude_match_region = ""
                        exclude_match_content = ""
                        if exclude:
                            compiled_excludes = kw_data.get('compiled_excludes')
                            if compiled_excludes is None:
                                compiled_excludes = []
                                for excl in exclude:
                                    if not excl:
                                        continue
                                    if use_regex:
                                        pattern = self.get_compiled_pattern(excl)
                                        compiled_excludes.append(('regex', pattern, excl))
                                    else:
                                        compiled_excludes.append(('text', None, excl))
                                kw_data['compiled_excludes'] = compiled_excludes
                            
                            # 排除文本参与附近检查：只检查附近字符区域（关键字前后指定字符数）
                            if exclude_nearby and kw_chars > 0 and matches_for_chars:
                                raw_nearby_chars = self._get_raw_nearby_chars_text(line, matches_for_chars, kw_chars)
                                if raw_nearby_chars:
                                    for excl_type, excl_pattern, excl_raw in compiled_excludes:
                                        if excl_type == 'regex':
                                            match = excl_pattern.search(raw_nearby_chars) if excl_pattern else None
                                            if match:
                                                excluded = True
                                                hit_exclude_text = excl_raw
                                                exclude_match_region = f"附近字符区域（前后{kw_chars}字符）"
                                                # 提取匹配内容及其上下文（前后各30字符）
                                                match_start = max(0, match.start() - 30)
                                                match_end = min(len(raw_nearby_chars), match.end() + 30)
                                                exclude_match_content = raw_nearby_chars[match_start:match_end].strip()
                                                break
                                        else:
                                            if excl_raw in raw_nearby_chars:
                                                excluded = True
                                                hit_exclude_text = excl_raw
                                                exclude_match_region = f"附近字符区域（前后{kw_chars}字符）"
                                                # 提取匹配内容及其上下文（前后各30字符）
                                                idx = raw_nearby_chars.find(excl_raw)
                                                if idx >= 0:
                                                    match_start = max(0, idx - 30)
                                                    match_end = min(len(raw_nearby_chars), idx + len(excl_raw) + 30)
                                                    exclude_match_content = raw_nearby_chars[match_start:match_end].strip()
                                                break
                                        if excluded:
                                            break
                            
                            # 多行关键字参与附近匹配过滤：检查附近行、上下行中是否包含排除文本
                            if multi_line_exclude and not excluded:
                                # 构建多行文本用于检查
                                multi_line_text_parts = []
                                region_parts = []
                                if nearby_lines_text:
                                    multi_line_text_parts.append(nearby_lines_text)
                                    region_parts.append("附近行")
                                if down_text:
                                    multi_line_text_parts.append(down_text)
                                    region_parts.append("向下行")
                                if up_text:
                                    multi_line_text_parts.append(up_text)
                                    region_parts.append("向上行")
                                
                                if multi_line_text_parts:
                                    multi_line_text = "\n".join(multi_line_text_parts)
                                    for excl_type, excl_pattern, excl_raw in compiled_excludes:
                                        if excl_type == 'regex':
                                            match = excl_pattern.search(multi_line_text) if excl_pattern else None
                                            if match:
                                                excluded = True
                                                hit_exclude_text = excl_raw
                                                exclude_match_region = "多行区域（" + "、".join(region_parts) + "）"
                                                # 提取匹配行及其上下文
                                                lines = multi_line_text.split('\n')
                                                match_line_idx = multi_line_text[:match.start()].count('\n')
                                                start_line = max(0, match_line_idx - 2)
                                                end_line = min(len(lines), match_line_idx + 3)
                                                exclude_match_content = '\n'.join(lines[start_line:end_line])
                                                break
                                        else:
                                            if excl_raw in multi_line_text:
                                                excluded = True
                                                hit_exclude_text = excl_raw
                                                exclude_match_region = "多行区域（" + "、".join(region_parts) + "）"
                                                # 提取匹配行及其上下文
                                                lines = multi_line_text.split('\n')
                                                for i, line in enumerate(lines):
                                                    if excl_raw in line:
                                                        start_line = max(0, i - 2)
                                                        end_line = min(len(lines), i + 3)
                                                        exclude_match_content = '\n'.join(lines[start_line:end_line])
                                                        break
                                                break
                                        if excluded:
                                            break
                        
                        if excluded:
                            keywords_display = " + ".join(words)
                            if remark:
                                keywords_display = f"（{remark}）{keywords_display}"
                            
                            # 使用与正常匹配相同的格式显示排除的关键字
                            display_nearby_lines = self.beautify_js(nearby_lines_text) if is_js else nearby_lines_text
                            display_nearby_chars = self.beautify_js(nearby_chars_text) if is_js else nearby_chars_text
                            display_down_text = self.beautify_js(down_text) if is_js else down_text
                            display_up_text = self.beautify_js(up_text) if is_js else up_text
                            
                            display_exclude = hit_exclude_text or "; ".join([e for e in exclude if e])
                            result_lines.append(f"关键字列表: {keywords_display}（位于第 {line_no} 行）[已排除: {display_exclude}]")
                            
                            # 显示附近行内容、附近文字等，与正常匹配格式一致
                            if kw_lines != -1:
                                result_lines.append("附近行内容:")
                                result_lines.append(display_nearby_lines)
                            if kw_chars > 0:
                                result_lines.append("附近文字:")
                                result_lines.append(display_nearby_chars)
                            if down_lines != 0:
                                direction = "向下" if down_lines > 0 else "向上"
                                result_lines.append(f"{direction}行内容:")
                                result_lines.append(display_down_text)
                            if up_lines != 0:
                                direction = "向上" if up_lines > 0 else "向下"
                                result_lines.append(f"{direction}行内容:")
                                result_lines.append(display_up_text)
                            
                            # 显示排除匹配的详细信息
                            if exclude_match_region:
                                result_lines.append(f"排除文本匹配区域: {exclude_match_region}")
                            if exclude_match_content:
                                # 限制显示长度，避免过长
                                if len(exclude_match_content) > 200:
                                    exclude_match_content = exclude_match_content[:200] + "..."
                                result_lines.append(f"排除文本匹配内容:\n{exclude_match_content}")
                            
                            result_lines.append("-" * 50)
                            
                            # 将被排除的结果也添加到 results 列表，添加 excluded 字段标记
                            nearby_lines_result = "" if kw_lines == -1 else (display_nearby_lines if is_js else nearby_lines_text)
                            results.append({
                                "keywords": keywords_display,
                                "keywords_raw": " + ".join(words),
                                "remark": remark,
                                "line_number": line_no,
                                "nearby_lines": nearby_lines_result,
                                "nearby_chars": display_nearby_chars if is_js else nearby_chars_text,
                                "down_lines": display_down_text if is_js else down_text,
                                "up_lines": display_up_text if is_js else up_text,
                                "source": os.path.basename(file_path),
                                "file_path": file_path,
                                "exclude_text": display_exclude,
                                "use_regex": use_regex,
                                "excluded": True,
                                "exclude_match_region": exclude_match_region,
                                "exclude_match_content": exclude_match_content
                            })
                            continue
                        
                        # 记录匹配结果
                        total_hits += 1
                        if total_hits == 1:
                            result_lines.append(f"文件路径: {file_path}")
                            result_lines.append(f"文件名: {os.path.basename(file_path)}")
                            result_lines.append("-" * 50)
                        
                        keywords_display = " + ".join(words)
                        if remark:
                            keywords_display = f"（{remark}）{keywords_display}"
                        
                        display_nearby_lines = self.beautify_js(nearby_lines_text) if is_js else nearby_lines_text
                        display_nearby_chars = self.beautify_js(nearby_chars_text) if is_js else nearby_chars_text
                        display_down_text = self.beautify_js(down_text) if is_js else down_text
                        display_up_text = self.beautify_js(up_text) if is_js else up_text
                        
                        result_lines.append(f"关键字列表: {keywords_display}（位于第 {line_no} 行）")
                        if kw_lines != -1:
                            result_lines.append("附近行内容:")
                            result_lines.append(display_nearby_lines)
                        if kw_chars > 0:
                            result_lines.append("附近文字:")
                            result_lines.append(display_nearby_chars)
                        if down_lines != 0:
                            direction = "向下" if down_lines > 0 else "向上"
                            result_lines.append(f"{direction}行内容:")
                            result_lines.append(display_down_text)
                        if up_lines != 0:
                            direction = "向上" if up_lines > 0 else "向下"
                            result_lines.append(f"{direction}行内容:")
                            result_lines.append(display_up_text)
                        result_lines.append("-" * 50)
                        
                        nearby_lines_result = "" if kw_lines == -1 else (display_nearby_lines if is_js else nearby_lines_text)
                        results.append({
                            "keywords": keywords_display,
                            "keywords_raw": " + ".join(words),
                            "remark": remark,
                            "line_number": line_no,
                            "nearby_lines": nearby_lines_result,
                            "nearby_chars": display_nearby_chars if is_js else nearby_chars_text,
                            "down_lines": display_down_text if is_js else down_text,
                            "up_lines": display_up_text if is_js else up_text,
                            "source": os.path.basename(file_path),
                            "file_path": file_path,
                            "exclude_text": "; ".join(exclude),
                            "use_regex": use_regex
                        })
                    
                    # 更新上下文窗口，准备处理下一行
                    if max_prev_lines > 0:
                        past_window.append(current_entry)
                        if len(past_window) > max_prev_lines:
                            past_window.popleft()
                    else:
                        past_window.clear()
                    
                    if future_window:
                        current_entry = future_window.popleft()
                    else:
                        current_entry = read_next_line()
                    
                    refill_future_buffer()
            
            if total_hits > 0:
                header = f"匹配到 {total_hits} 个关键字列表"
                result_lines.insert(3, header)
            
            result_text = "\n".join(result_lines)
            return result_text, results
            
        except Exception as e:
            print(f"流式处理文件 {file_path} 时出错: {str(e)}")
            return "", []
    
    def _check_line_match_optimized(self, line, words, use_regex, multi_line_exclude, 
                                   context_window, line_no, kw_lines, down_lines, up_lines,
                                   compiled_patterns):
        """检查行是否匹配关键字（优化版本，使用预编译的模式和快速路径）"""
        if not words:
            return False
        
        if use_regex:
            # 正则表达式模式：第一个关键字在当前行匹配
            first_word_pattern = compiled_patterns.get(words[0])
            if not first_word_pattern or not first_word_pattern.search(line):
                return False
            if len(words) > 1:
                # 多个关键字：其他关键字在附近行范围内匹配
                combined_content = self._get_combined_context(
                    context_window, line_no, kw_lines, down_lines, up_lines
                )
                # 快速失败：一旦找到不匹配的关键字就返回
                for word in words[1:]:
                    pattern = compiled_patterns.get(word)
                    if not pattern or not pattern.search(combined_content):
                        return False
            return True
        else:
            # 普通文本模式
            if len(words) > 1:
                # 多个关键字：第一个在当前行，其他在附近行范围内匹配
                if words[0] not in line:
                    return False
                other_keywords = words[1:]
                if other_keywords:
                    # 延迟获取上下文，只在需要时计算
                    combined_content = self._get_combined_context(
                        context_window, line_no, kw_lines, down_lines, up_lines
                    )
                    # 快速失败：一旦找到不匹配的关键字就返回
                    for word in other_keywords:
                        if word and word not in combined_content:
                            return False
                return True
            else:
                # 单个关键字，直接使用in操作符（最快）
                return words[0] in line
    
    def _check_line_match(self, line, words, use_regex, multi_line_exclude, 
                         context_window, line_no, kw_lines, down_lines, up_lines):
        """检查行是否匹配关键字（兼容旧版本，已优化多关键字匹配）"""
        if use_regex:
            # 正则表达式模式：第一个关键字在当前行匹配
            first_word_pattern = self.get_compiled_pattern(words[0]) if words else None
            if not first_word_pattern or not first_word_pattern.search(line):
                return False
            if len(words) > 1:
                # 多个关键字：其他关键字在附近行范围内匹配
                combined_content = self._get_combined_context(
                    context_window, line_no, kw_lines, down_lines, up_lines
                )
                for word in words[1:]:
                    pattern = self.get_compiled_pattern(word)
                    if not pattern or not pattern.search(combined_content):
                        return False
            return True
        else:
            # 普通文本模式
            if len(words) > 1:
                # 多个关键字：第一个在当前行，其他在附近行范围内匹配
                if words[0] not in line:
                    return False
                other_keywords = words[1:]
                if other_keywords:
                    combined_content = self._get_combined_context(
                        context_window, line_no, kw_lines, down_lines, up_lines
                    )
                    return all(word in combined_content for word in other_keywords if word)
                return True
            else:
                # 单个关键字，在当前行匹配
                return words[0] in line if words else False
    
    def _get_nearby_lines_from_window(self, context_window, line_no, kw_lines):
        """从滑动窗口获取附近行"""
        if kw_lines == -1:
            return ""
        lines_list = []
        for win_line_no, win_line in context_window:
            if abs(win_line_no - line_no) <= kw_lines:
                lines_list.append(win_line)
        return "\n".join(lines_list)
    
    def _get_down_text_from_window(self, context_window, line_no, down_lines):
        """从滑动窗口获取向下行"""
        if down_lines == 0:
            return ""
        lines_list = []
        for win_line_no, win_line in context_window:
            if down_lines > 0:
                # 向下行数包含关键字所在行（作为第一行）和向下指定行数
                # 例如：down_lines=1 应该包含 line_no 和 line_no+1
                if line_no <= win_line_no <= line_no + down_lines:
                    lines_list.append(win_line)
            else:
                # 负数的向下行数（向上行）
                if line_no + down_lines <= win_line_no < line_no:
                    lines_list.append(win_line)
        return "\n".join(lines_list)
    
    def _get_up_text_from_window(self, context_window, line_no, up_lines):
        """从滑动窗口获取向上行"""
        if up_lines == 0:
            return ""
        lines_list = []
        for win_line_no, win_line in context_window:
            if up_lines > 0:
                if line_no - 1 - up_lines < win_line_no < line_no:
                    lines_list.append(win_line)
            else:
                if line_no < win_line_no <= line_no - up_lines:
                    lines_list.append(win_line)
        return "\n".join(lines_list)
    
    def _get_combined_context(self, context_window, line_no, kw_lines, down_lines, up_lines):
        """获取组合上下文"""
        parts = []
        if kw_lines != -1:
            parts.append(self._get_nearby_lines_from_window(context_window, line_no, kw_lines))
        if down_lines != 0:
            parts.append(self._get_down_text_from_window(context_window, line_no, down_lines))
        if up_lines != 0:
            parts.append(self._get_up_text_from_window(context_window, line_no, up_lines))
        return "\n".join(parts)
    
    def _get_nearby_chars(self, line, first_keyword, kw_chars, use_regex):
        """获取附近字符"""
        if kw_chars <= 0 or not first_keyword:
            return ""
        if use_regex:
            pattern = self.get_compiled_pattern(first_keyword)
            if pattern:
                matches = list(pattern.finditer(line))
                return self._build_char_snippets(line, matches, kw_chars)
        else:
            pattern = re.compile(r'(' + re.escape(first_keyword) + ')')
            matches = list(pattern.finditer(line))
            return self._build_char_snippets(line, matches, kw_chars)
        return ""

    def process_text(self, text, file_path):
        """处理单个文件的文本"""
        keywords = self.config["keywords"]
        default_nearby_lines = self.config["nearby_lines"]
        default_nearby_chars = self.config["nearby_chars"]
        
        # 检查是否为JS文件
        is_js = self.is_js_file(file_path)

        results = []
        result_lines = []
        total_hits = 0
        lines = text.splitlines()

        for kw_config in keywords:
            words = kw_config.get("words", [])
            exclude = kw_config.get("exclude", [])
            kw_lines = kw_config.get("nearby_lines", default_nearby_lines)
            kw_chars = kw_config.get("nearby_chars", default_nearby_chars)
            down_lines = kw_config.get("down_lines", self.config.get("down_lines", 0))
            up_lines = kw_config.get("up_lines", self.config.get("up_lines", 0))
            exclude_nearby = kw_config.get("exclude_nearby", True)
            multi_line_exclude = kw_config.get("multi_line_exclude", False)
            use_regex = kw_config.get("use_regex", False)
            remark = kw_config.get("remark", "").strip()  # 获取备注信息

            # 预编译正则表达式
            compiled_patterns = {}
            if use_regex:
                for word in words:
                    if word:
                        try:
                            compiled_patterns[word] = self.get_compiled_pattern(word)
                        except Exception as e:
                            print(f"正则表达式编译错误 '{word}': {e}")
                            compiled_patterns[word] = None
                for excl in exclude:
                    if excl:
                        try:
                            compiled_patterns[excl] = self.get_compiled_pattern(excl)
                        except Exception as e:
                            print(f"排除正则表达式编译错误 '{excl}': {e}")
                            compiled_patterns[excl] = None
            else:
                # 仅针对第一个关键字构建字符截取用的正则
                if kw_chars > 0 and words[:1]:
                    first_keyword = words[0]
                    plain_char_pattern = re.compile(r'(' + re.escape(first_keyword) + ')') if first_keyword else None
                else:
                    plain_char_pattern = None

            for line_no, line in enumerate(lines, 1):
                if not words:
                    continue

                context_cache = {}

                def get_nearby_lines_text():
                    if kw_lines == -1:
                        return ""
                    cached = context_cache.get("nearby_lines")
                    if cached is not None:
                        return cached
                    # line_no 是从1开始的行号，需要转换为从0开始的索引
                    start_line = max(0, line_no - 1 - kw_lines)
                    end_line = min(len(lines), line_no - 1 + kw_lines + 1)  # 转换为索引，包含关键字所在行和上下行
                    text_block = "\n".join(lines[start_line:end_line])
                    context_cache["nearby_lines"] = text_block
                    return text_block

                def get_down_text():
                    cached = context_cache.get("down_text")
                    if cached is not None:
                        return cached
                    if down_lines == 0:
                        context_cache["down_text"] = ""
                        return ""
                    if down_lines > 0:
                        # line_no 是从1开始的行号，需要转换为从0开始的索引
                        # 向下行数包含关键字所在行（作为第一行）和向下指定行数
                        down_start = line_no - 1  # 转换为索引，包含关键字所在行
                        down_end = min(len(lines), line_no - 1 + down_lines + 1)  # 包含关键字所在行和向下行
                    else:
                        # 负数的向下行数（向上行）
                        down_start = max(0, line_no - 1 + down_lines)
                        down_end = line_no  # line_no 是行号，需要转换为索引
                    text_block = "\n".join(lines[down_start:down_end])
                    context_cache["down_text"] = text_block
                    return text_block

                def get_up_text():
                    cached = context_cache.get("up_text")
                    if cached is not None:
                        return cached
                    if up_lines == 0:
                        context_cache["up_text"] = ""
                        return ""
                    if up_lines > 0:
                        up_start = max(0, line_no - 1 - up_lines)
                        up_end = line_no - 1
                    else:
                        up_start = line_no - 1
                        up_end = min(len(lines), line_no - 1 - up_lines)
                    text_block = "\n".join(lines[up_start:up_end])
                    context_cache["up_text"] = text_block
                    return text_block

                def get_nearby_chars_text():
                    if kw_chars <= 0:
                        return ""
                    cached = context_cache.get("nearby_chars")
                    if cached is not None:
                        return cached
                    if use_regex:
                        first_word = words[0] if words else None
                        pattern = compiled_patterns.get(first_word) if first_word else None
                        if pattern is None:
                            context_cache["nearby_chars"] = "正则表达式语法错误"
                            return context_cache["nearby_chars"]
                        matches = list(pattern.finditer(line))
                    else:
                        if plain_char_pattern is None:
                            context_cache["nearby_chars"] = ""
                            return ""
                        matches = list(plain_char_pattern.finditer(line))
                    snippets = self._build_char_snippets(line, matches, kw_chars)
                    context_cache["nearby_chars"] = snippets
                    return snippets

                # 检查匹配 - 优化多关键字匹配逻辑
                match_success = False
                
                if use_regex:
                    # 正则表达式模式
                    try:
                        first_word_pattern = compiled_patterns.get(words[0]) if words else None
                        if first_word_pattern and first_word_pattern.search(line):
                            if len(words) > 1:
                                # 多个关键字：第一个在当前行匹配，其他在附近行范围内匹配
                                # 组合所有相关内容进行多行匹配
                                combined_content = "\n".join(filter(None, [
                                    line,
                                    get_nearby_lines_text(),
                                    get_down_text(),
                                    get_up_text()
                                ]))
                                all_found = True
                                for i, word in enumerate(words[1:], 1):  # 从第二个关键字开始检查
                                    if word:
                                        word_pattern = compiled_patterns.get(word)
                                        if word_pattern is None or not word_pattern.search(combined_content):
                                            all_found = False
                                            break
                                if all_found:
                                    match_success = True
                            else:
                                # 只有一个关键字，直接匹配成功
                                match_success = True
                    except re.error:
                        match_success = False
                else:
                    # 普通文本模式
                    if len(words) > 1:
                        # 多个关键字：第一个在当前行匹配，其他在附近行范围内匹配
                        if any(w in line for w in words[0:1]):
                            other_keywords = words[1:]
                            if other_keywords:
                                combined_content = (
                                    line + "\n" +
                                    get_nearby_lines_text() + "\n" +
                                    (get_nearby_chars_text() if kw_chars > 0 else "") + "\n" +
                                    get_down_text() + "\n" +
                                    get_up_text()
                                )
                                all_found = all(word in combined_content for word in other_keywords if word)
                                if all_found:
                                    match_success = True
                            else:
                                match_success = True
                    else:
                        # 只有一个关键字，在当前行匹配
                        all_found = all(word in line for word in words if word)
                        if all_found:
                            match_success = True

                if not match_success:
                    continue

                # 延迟获取上下文，确保只在匹配时计算
                nearby_lines_text = "" if kw_lines == -1 else get_nearby_lines_text()
                down_text = get_down_text()
                up_text = get_up_text()
                nearby_chars_text = get_nearby_chars_text() if kw_chars > 0 else ""

                # 检查排除文本：根据配置分别检查不同区域，并记录命中的排除文本
                excluded = False
                hit_exclude_text = ""
                exclude_match_region = ""
                exclude_match_content = ""
                if exclude:
                    # 排除文本参与附近检查：只检查附近字符区域（关键字前后指定字符数）
                    if exclude_nearby and kw_chars > 0:
                        # 获取原始附近字符文本用于排除检查
                        raw_nearby_chars = ""
                        matches_for_exclude = []
                        if use_regex:
                            first_word = words[0] if words else None
                            pattern = compiled_patterns.get(first_word) if first_word else None
                            if pattern:
                                matches_for_exclude = list(pattern.finditer(line))
                        else:
                            if plain_char_pattern:
                                matches_for_exclude = list(plain_char_pattern.finditer(line))
                        
                        if matches_for_exclude:
                            raw_nearby_chars = self._get_raw_nearby_chars_text(line, matches_for_exclude, kw_chars)
                        
                        if raw_nearby_chars:
                            if use_regex:
                                try:
                                    for excl in exclude:
                                        if excl:
                                            pattern = compiled_patterns.get(excl)
                                            if pattern is not None:
                                                match = pattern.search(raw_nearby_chars)
                                                if match:
                                                    excluded = True
                                                    hit_exclude_text = excl
                                                    exclude_match_region = f"附近字符区域（前后{kw_chars}字符）"
                                                    # 提取匹配内容及其上下文（前后各30字符）
                                                    match_start = max(0, match.start() - 30)
                                                    match_end = min(len(raw_nearby_chars), match.end() + 30)
                                                    exclude_match_content = raw_nearby_chars[match_start:match_end].strip()
                                                    break
                                except re.error:
                                    excluded = False
                            else:
                                for e in exclude:
                                    if e and e in raw_nearby_chars:
                                        excluded = True
                                        hit_exclude_text = e
                                        exclude_match_region = f"附近字符区域（前后{kw_chars}字符）"
                                        # 提取匹配内容及其上下文（前后各30字符）
                                        idx = raw_nearby_chars.find(e)
                                        if idx >= 0:
                                            match_start = max(0, idx - 30)
                                            match_end = min(len(raw_nearby_chars), idx + len(e) + 30)
                                            exclude_match_content = raw_nearby_chars[match_start:match_end].strip()
                                        break
                    
                    # 多行关键字参与附近匹配过滤：检查附近行、上下行中是否包含排除文本
                    if multi_line_exclude and not excluded:
                        # 构建多行文本用于检查
                        multi_line_text_parts = []
                        region_parts = []
                        if nearby_lines_text:
                            multi_line_text_parts.append(nearby_lines_text)
                            region_parts.append("附近行")
                        if down_text:
                            multi_line_text_parts.append(down_text)
                            region_parts.append("向下行")
                        if up_text:
                            multi_line_text_parts.append(up_text)
                            region_parts.append("向上行")
                        
                        if multi_line_text_parts:
                            multi_line_text = "\n".join(multi_line_text_parts)
                            if use_regex:
                                try:
                                    for excl in exclude:
                                        if excl:
                                            pattern = compiled_patterns.get(excl)
                                            if pattern is not None:
                                                match = pattern.search(multi_line_text)
                                                if match:
                                                    excluded = True
                                                    hit_exclude_text = excl
                                                    exclude_match_region = "多行区域（" + "、".join(region_parts) + "）"
                                                    # 提取匹配行及其上下文
                                                    lines = multi_line_text.split('\n')
                                                    match_line_idx = multi_line_text[:match.start()].count('\n')
                                                    start_line = max(0, match_line_idx - 2)
                                                    end_line = min(len(lines), match_line_idx + 3)
                                                    exclude_match_content = '\n'.join(lines[start_line:end_line])
                                                    break
                                except re.error:
                                    excluded = False
                            else:
                                for e in exclude:
                                    if e and e in multi_line_text:
                                        excluded = True
                                        hit_exclude_text = e
                                        exclude_match_region = "多行区域（" + "、".join(region_parts) + "）"
                                        # 提取匹配行及其上下文
                                        lines = multi_line_text.split('\n')
                                        for i, line in enumerate(lines):
                                            if e in line:
                                                start_line = max(0, i - 2)
                                                end_line = min(len(lines), i + 3)
                                                exclude_match_content = '\n'.join(lines[start_line:end_line])
                                                break
                                        break

                if excluded:
                    # 如果有备注，在关键字前添加备注
                    keywords_display = " + ".join(words)
                    if remark:
                        keywords_display = f"（{remark}）{keywords_display}"
                    
                    # 使用与正常匹配相同的格式显示排除的关键字
                    display_nearby_lines = self.beautify_js(nearby_lines_text) if is_js else nearby_lines_text
                    display_nearby_chars = self.beautify_js(nearby_chars_text) if is_js else nearby_chars_text
                    display_down_text = self.beautify_js(down_text) if is_js else down_text
                    display_up_text = self.beautify_js(up_text) if is_js else up_text
                    
                    display_exclude = hit_exclude_text or "; ".join([e for e in exclude if e])
                    result_lines.append(f"关键字列表: {keywords_display}（位于第 {line_no} 行）[已排除: {display_exclude}]")
                    
                    # 显示附近行内容、附近文字等，与正常匹配格式一致
                    if kw_lines != -1:
                        result_lines.append("附近行内容:")
                        result_lines.append(display_nearby_lines)
                    if kw_chars > 0:
                        result_lines.append("附近文字:")
                        result_lines.append(display_nearby_chars)
                    if down_lines != 0:
                        direction = "向下" if down_lines > 0 else "向上"
                        result_lines.append(f"{direction}行内容:")
                        result_lines.append(display_down_text)
                    if up_lines != 0:
                        direction = "向上" if up_lines > 0 else "向下"
                        result_lines.append(f"{direction}行内容:")
                        result_lines.append(display_up_text)
                    
                    # 显示排除匹配的详细信息
                    if exclude_match_region:
                        result_lines.append(f"排除文本匹配区域: {exclude_match_region}")
                    if exclude_match_content:
                        # 限制显示长度，避免过长
                        if len(exclude_match_content) > 200:
                            exclude_match_content = exclude_match_content[:200] + "..."
                        result_lines.append(f"排除文本匹配内容:\n{exclude_match_content}")
                    
                    result_lines.append("-" * 50)
                    
                    # 将被排除的结果也添加到 results 列表，添加 excluded 字段标记
                    nearby_lines_result = ""
                    if kw_lines != -1:
                        nearby_lines_result = display_nearby_lines if is_js else nearby_lines_text
                    results.append({
                        "keywords": keywords_display,  # 使用包含备注的关键字显示
                        "keywords_raw": " + ".join(words),  # 保存原始关键字（不含备注）
                        "remark": remark,  # 保存备注信息
                        "line_number": line_no,
                        "nearby_lines": nearby_lines_result,  # 如果kw_lines为-1，则为空字符串
                        "nearby_chars": display_nearby_chars if is_js else nearby_chars_text,  # JS文件保存美化后的内容
                        "down_lines": display_down_text if is_js else down_text,  # JS文件保存美化后的内容
                        "up_lines": display_up_text if is_js else up_text,  # JS文件保存美化后的内容
                        "source": os.path.basename(file_path),
                        "file_path": file_path,
                        "exclude_text": display_exclude,
                        "use_regex": use_regex,
                        "excluded": True,
                        "exclude_match_region": exclude_match_region,
                        "exclude_match_content": exclude_match_content
                    })
                    continue

                # 记录匹配结果
                total_hits += 1
                if total_hits == 1:
                    result_lines.append(f"文件路径: {file_path}")
                    result_lines.append(f"文件名: {os.path.basename(file_path)}")
                    result_lines.append("-" * 50)

                # 如果有备注，在关键字前添加备注
                keywords_display = " + ".join(words)
                if remark:
                    keywords_display = f"（{remark}）{keywords_display}"
                
                # 如果是JS文件，美化输出内容
                display_nearby_lines = self.beautify_js(nearby_lines_text) if is_js else nearby_lines_text
                display_nearby_chars = self.beautify_js(nearby_chars_text) if is_js else nearby_chars_text
                display_down_text = self.beautify_js(down_text) if is_js else down_text
                display_up_text = self.beautify_js(up_text) if is_js else up_text
                
                result_lines.append(f"关键字列表: {keywords_display}（位于第 {line_no} 行）")
                # 只有当kw_lines不为-1时才输出附近行内容
                if kw_lines != -1:
                    result_lines.append("附近行内容:")
                    result_lines.append(display_nearby_lines)
                if kw_chars > 0:
                    result_lines.append("附近文字:")
                    result_lines.append(display_nearby_chars)
                if down_lines != 0:
                    direction = "向下" if down_lines > 0 else "向上"
                    result_lines.append(f"{direction}行内容:")
                    result_lines.append(display_down_text)
                if up_lines != 0:
                    direction = "向上" if up_lines > 0 else "向下"
                    result_lines.append(f"{direction}行内容:")
                    result_lines.append(display_up_text)
                result_lines.append("-" * 50)

                # 对于结果字典，如果是JS文件也保存美化后的内容
                # 如果kw_lines为-1，nearby_lines字段保存空字符串
                nearby_lines_result = ""
                if kw_lines != -1:
                    nearby_lines_result = display_nearby_lines if is_js else nearby_lines_text
                
                results.append({
                    "keywords": keywords_display,  # 使用包含备注的关键字显示
                    "keywords_raw": " + ".join(words),  # 保存原始关键字（不含备注）
                    "remark": remark,  # 保存备注信息
                    "line_number": line_no,
                    "nearby_lines": nearby_lines_result,  # 如果kw_lines为-1，则为空字符串
                    "nearby_chars": display_nearby_chars if is_js else nearby_chars_text,  # JS文件保存美化后的内容
                    "down_lines": display_down_text if is_js else down_text,  # JS文件保存美化后的内容
                    "up_lines": display_up_text if is_js else up_text,  # JS文件保存美化后的内容
                    "source": os.path.basename(file_path),
                    "file_path": file_path,
                    "exclude_text": "; ".join(exclude),
                    "use_regex": use_regex
                })

        if total_hits > 0:
            header = f"匹配到 {total_hits} 个关键字列表"
            result_lines.insert(3, header)

        result_text = "\n".join(result_lines)
        return result_text, results