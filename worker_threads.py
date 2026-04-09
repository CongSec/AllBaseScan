# -*- coding: utf-8 -*-
import os
import sys
import multiprocessing
import atexit
import threading
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from PyQt5.QtCore import QThread, pyqtSignal, QMutex, QWaitCondition
from text_processor import TextProcessor
from constants import MAX_WORKER_PROCESSES

# 全局变量，用于跟踪所有活动的进程池
_active_executors = []
# 在Windows上使用threading.Lock，因为multiprocessing.Lock在spawn模式下可能无法正确序列化
_active_executors_lock = threading.Lock()

def _cleanup_executors():
    """清理所有活动的进程池（在程序退出时调用）"""
    _force_cleanup_all_executors()

def _get_executor_processes(executor):
    """获取进程池中的所有进程（兼容不同Python版本）"""
    processes = []
    if executor is None:
        return processes
    
    # 尝试不同的属性名（不同Python版本可能不同）
    # ProcessPoolExecutor内部使用_processes字典存储进程
    for attr_name in ['_processes', '_workers', '_pool']:
        if hasattr(executor, attr_name):
            try:
                attr = getattr(executor, attr_name)
                if isinstance(attr, dict):
                    # 字典类型，提取所有值
                    for value in attr.values():
                        if value is not None:
                            processes.append(value)
                elif isinstance(attr, (list, tuple)):
                    # 列表或元组类型
                    processes.extend(attr)
                elif attr is not None:
                    # 单个对象
                    processes.append(attr)
            except (AttributeError, RuntimeError, OSError):
                # 忽略访问错误，继续尝试其他属性
                pass
    
    # 进一步尝试通过内部属性获取进程
    # ProcessPoolExecutor._adjust_process_count可能包含进程信息
    try:
        if hasattr(executor, '_adjust_process_count'):
            # 某些版本可能在_adjust_process_count中
            pass
    except:
        pass
    
    # 过滤掉 None 值，并确保是 Process 对象
    valid_processes = []
    seen_pids = set()  # 用于去重
    for p in processes:
        if p is None:
            continue
        try:
            # 检查是否是Process对象
            if hasattr(p, 'is_alive') and hasattr(p, 'pid'):
                # 通过pid去重，避免重复添加同一个进程
                try:
                    pid = p.pid
                    if pid not in seen_pids:
                        seen_pids.add(pid)
                        valid_processes.append(p)
                except (AttributeError, ValueError):
                    # 如果无法获取pid，直接添加（可能是进程已退出）
                    valid_processes.append(p)
        except (AttributeError, RuntimeError, OSError):
            # 忽略访问错误
            pass
    
    return valid_processes

def _terminate_process_forcefully(process):
    """强制终止单个进程（所有平台）"""
    if not process:
        return
    
    try:
        # 检查进程是否还活着
        if not hasattr(process, 'is_alive'):
            return
        try:
            if not process.is_alive():
                return
        except (OSError, ValueError, AttributeError):
            # 进程可能已经退出或无法访问
            return
    except (OSError, ValueError, AttributeError):
        # 如果检查失败，假设进程已死
        return
    
    # 获取进程PID
    pid = None
    try:
        if hasattr(process, 'pid'):
            pid = process.pid
    except:
        pass
    
    # Windows上使用更强制的方法
    if sys.platform == 'win32' and pid:
        try:
            import subprocess
            # 使用taskkill强制终止进程及其子进程
            subprocess.run(
                ['taskkill', '/F', '/T', '/PID', str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=2
            )
            time.sleep(0.1)
            return
        except:
            # 如果taskkill失败，继续使用标准方法
            pass
    
    try:
        # 先尝试优雅终止
        if hasattr(process, 'terminate'):
            process.terminate()
            time.sleep(0.3)  # 给进程一些时间退出
            
            # 检查是否还在运行
            try:
                if process.is_alive():
                    # 如果还在运行，再次尝试terminate
                    process.terminate()
                    time.sleep(0.3)
                    
                    # 如果还在运行，尝试kill（Unix系统）
                    if hasattr(process, 'kill'):
                        try:
                            process.kill()
                            time.sleep(0.1)
                        except (OSError, ProcessLookupError):
                            # 进程可能已经退出
                            pass
            except (OSError, ValueError, AttributeError):
                # 进程可能已经退出，无法检查状态
                pass
    except (OSError, ProcessLookupError, AttributeError):
        # 如果 terminate 失败，直接尝试 kill
        try:
            if hasattr(process, 'kill'):
                process.kill()
                time.sleep(0.1)
        except (OSError, ProcessLookupError, AttributeError):
            # 进程可能已经退出
            pass

def _force_cleanup_all_executors():
    """强制清理所有活动的进程池和子进程"""
    executors_to_clean = []
    try:
        _active_executors_lock.acquire()
        executors_to_clean = _active_executors[:]
    finally:
        _active_executors_lock.release()
    
    for executor in executors_to_clean:
        try:
            # 在关闭前，先获取所有子进程
            processes = _get_executor_processes(executor)
            
            # 强制关闭，不等待
            try:
                if sys.version_info >= (3, 9):
                    executor.shutdown(wait=False, cancel_futures=True)
                else:
                    executor.shutdown(wait=False)
            except:
                # 如果 shutdown 失败，继续尝试终止子进程
                pass
            
            # 强制终止所有子进程（所有平台）
            if processes:
                for process in processes:
                    _terminate_process_forcefully(process)
            
            # 等待进程退出，但设置超时避免无限等待
            if processes:
                max_wait_time = 3.0  # 最多等待3秒
                start_time = time.time()
                alive_processes = processes[:]
                
                # 轮询检查进程状态
                while alive_processes and (time.time() - start_time) < max_wait_time:
                    remaining_processes = []
                    for process in alive_processes:
                        try:
                            if hasattr(process, 'is_alive') and process.is_alive():
                                remaining_processes.append(process)
                            elif hasattr(process, 'join'):
                                try:
                                    process.join(timeout=0.1)
                                except:
                                    pass
                        except (OSError, ValueError, AttributeError):
                            # 进程可能已经退出
                            pass
                    alive_processes = remaining_processes
                    if alive_processes:
                        time.sleep(0.1)
                
                # 如果超时后仍有进程存活，强制终止
                if alive_processes:
                    for process in alive_processes:
                        _terminate_process_forcefully(process)
                
                # 第二轮：再次检查并强制终止仍在运行的进程
                time.sleep(0.3)
                for process in processes:
                    try:
                        if hasattr(process, 'is_alive') and process.is_alive():
                            _terminate_process_forcefully(process)
                    except (OSError, ValueError, AttributeError):
                        # 进程可能已经退出
                        pass
                
                # 第三轮：最后检查，确保所有进程都已退出
                time.sleep(0.2)
                for process in processes:
                    try:
                        if hasattr(process, 'is_alive') and process.is_alive():
                            _terminate_process_forcefully(process)
                    except (OSError, ValueError, AttributeError):
                        # 进程可能已经退出
                        pass
        except Exception:
            pass
    
    # 清空列表
    try:
        _active_executors_lock.acquire()
        _active_executors.clear()
    finally:
        _active_executors_lock.release()

# 注册退出时的清理函数
atexit.register(_cleanup_executors)

# 导出清理函数，供外部调用
def cleanup_all_processes():
    """外部调用的清理函数，强制清理所有进程池和子进程"""
    _force_cleanup_all_executors()

# Windows上需要设置spawn启动方法以确保多进程正常工作
# 注意：这必须在导入模块时设置，但可能已经设置过了
if sys.platform == 'win32':
    try:
        # 尝试获取当前启动方法
        current_method = multiprocessing.get_start_method(allow_none=True)
        if current_method != 'spawn':
            try:
                multiprocessing.set_start_method('spawn', force=True)
            except RuntimeError:
                # 如果已经设置过，尝试不强制设置
                try:
                    multiprocessing.set_start_method('spawn')
                except RuntimeError:
                    # 如果还是失败，使用默认方法
                    pass
    except ValueError:
        # 如果还没有设置，设置spawn方法
        try:
            multiprocessing.set_start_method('spawn')
        except RuntimeError:
            pass

def _process_file_worker(args):
    """多进程工作函数 - 处理单个文件（必须是模块级函数以便pickle序列化）"""
    file_path, config, auto_detect_encoding = args
    try:
        # 在每个进程中重新创建processor（避免共享状态问题）
        processor = TextProcessor(config, auto_detect_encoding)
        result_text, file_results = processor.process_file_streaming(file_path, progress_callback=None)
        return {
            'success': True,
            'file_path': file_path,
            'result_text': result_text,
            'results': file_results,
            'error': None
        }
    except Exception as e:
        import traceback
        error_msg = f"{str(e)}\n{traceback.format_exc()}"
        return {
            'success': False,
            'file_path': file_path,
            'result_text': '',
            'results': [],
            'error': error_msg
        }

class WorkerThread(QThread):
    progress_signal = pyqtSignal(int, int, str)
    result_signal = pyqtSignal(str, list)
    finished_signal = pyqtSignal()
    error_signal = pyqtSignal(str)
    line_progress_signal = pyqtSignal(int, str)  # 新增：行处理进度信号

    def __init__(self, config, files, auto_detect_encoding=True, max_workers=None):
        super().__init__()
        self.config = config
        self.files = files
        self.is_running = True
        self.auto_detect_encoding = auto_detect_encoding
        
        # 计算最大进程数
        # 限制最大进程数，避免在高核数CPU上创建过多进程
        # 即使CPU核心数很多，也不应该创建超过MAX_WORKER_PROCESSES个进程
        if max_workers is None:
            max_workers = min(MAX_WORKER_PROCESSES, len(files))
        else:
            # 确保不超过合理范围，严格限制在MAX_WORKER_PROCESSES内
            max_workers = min(max_workers, MAX_WORKER_PROCESSES, len(files))
        
        # 确保至少为1
        self.max_workers = max(1, max_workers)
        self.current_file = None
        self.mutex = QMutex()
        self.condition = QWaitCondition()
        self.executor = None  # 保存进程池引用，以便可以强制关闭

    def _line_progress_callback(self, line_no):
        """行处理进度回调"""
        if self.current_file and self.is_running:
            self.line_progress_signal.emit(line_no, self.current_file)

    def run(self):
        try:
            total_files = len(self.files)
            all_results = []
            result_texts = []
            processed_count = 0

            # 如果文件数量少或只有一个CPU核心，使用单进程模式（避免进程开销）
            if total_files <= 2 or self.max_workers <= 1:
                # 单进程模式（保持原有逻辑，但优化性能）
                processor = TextProcessor(self.config, self.auto_detect_encoding)
                for i, file_path in enumerate(self.files):
                    if not self.is_running:
                        break
                    self.current_file = os.path.basename(file_path)
                    self.progress_signal.emit(i + 1, total_files, self.current_file)
                    try:
                        result_text, file_results = processor.process_file_streaming(
                            file_path, 
                            progress_callback=self._line_progress_callback
                        )
                        # 即使只有“已排除”提示、没有实际匹配结果，也应该保留文本结果
                        if file_results:
                            all_results.extend(file_results)
                        if result_text and result_text.strip():
                            result_texts.append(result_text)
                    except Exception as e:
                        self.error_signal.emit(f"读取文件 {file_path} 时出错: {str(e)}")
                        continue
                    finally:
                        self.current_file = None
            else:
                # 多进程并发模式 - 充分利用多核CPU
                # 准备参数列表
                process_args = [
                    (file_path, self.config, self.auto_detect_encoding)
                    for file_path in self.files
                ]
                
                # 使用进程池并发处理
                self.executor = None
                try:
                    self.executor = ProcessPoolExecutor(max_workers=self.max_workers)
                    try:
                        _active_executors_lock.acquire()
                        _active_executors.append(self.executor)
                    finally:
                        _active_executors_lock.release()
                except Exception as e:
                    self.error_signal.emit(f"创建进程池失败: {str(e)}")
                    return
                
                try:
                    # 提交所有任务
                    future_to_file = {
                        self.executor.submit(_process_file_worker, args): args[0]
                        for args in process_args
                    }
                    
                    # 收集结果（按完成顺序）
                    completed_futures = []
                    for future in as_completed(future_to_file):
                        if not self.is_running:
                            # 取消未完成的任务
                            for f in future_to_file:
                                if not f.done():
                                    f.cancel()
                            break
                        
                        file_path = future_to_file[future]
                        try:
                            result = future.result(timeout=None)
                            processed_count += 1
                            
                            # 更新进度
                            self.mutex.lock()
                            self.current_file = os.path.basename(file_path)
                            self.progress_signal.emit(processed_count, total_files, self.current_file)
                            self.mutex.unlock()
                            
                            if result['success']:
                                # 结果列表只包含真正的命中，但文本可能只有“已排除”提示
                                if result['results']:
                                    all_results.extend(result['results'])
                                if result['result_text'] and result['result_text'].strip():
                                    result_texts.append(result['result_text'])
                            else:
                                self.error_signal.emit(f"读取文件 {file_path} 时出错: {result['error']}")
                        except Exception as e:
                            self.error_signal.emit(f"处理文件 {file_path} 时出错: {str(e)}")
                        finally:
                            completed_futures.append(future)
                finally:
                    # 确保进程池被正确关闭（无论是否正常完成）
                    if self.executor:
                        executor_to_clean = self.executor
                        self.executor = None  # 先清空引用，避免重复清理
                        
                        try:
                            # 先获取所有子进程
                            processes = _get_executor_processes(executor_to_clean)
                            
                            # 如果 is_running 为 False，强制终止所有进程
                            if not self.is_running:
                                # 强制关闭，不等待任务完成
                                try:
                                    if sys.version_info >= (3, 9):
                                        executor_to_clean.shutdown(wait=False, cancel_futures=True)
                                    else:
                                        executor_to_clean.shutdown(wait=False)
                                except Exception:
                                    try:
                                        executor_to_clean.shutdown(wait=False)
                                    except:
                                        pass
                            else:
                                # 正常关闭，但设置超时避免无限等待
                                # 使用shutdown(wait=False)然后手动等待，这样可以控制超时
                                try:
                                    # 先尝试取消未完成的任务
                                    if sys.version_info >= (3, 9):
                                        executor_to_clean.shutdown(wait=False, cancel_futures=True)
                                    else:
                                        executor_to_clean.shutdown(wait=False)
                                    
                                    # 手动等待进程完成，但设置更短的超时（避免卡死）
                                    if processes:
                                        max_wait_time = 5.0  # 最多等待5秒（减少等待时间，避免卡死）
                                        start_time = time.time()
                                        alive_processes = processes[:]
                                        
                                        # 轮询检查进程状态
                                        while alive_processes and (time.time() - start_time) < max_wait_time:
                                            remaining_processes = []
                                            for process in alive_processes:
                                                try:
                                                    if hasattr(process, 'is_alive') and process.is_alive():
                                                        remaining_processes.append(process)
                                                    elif hasattr(process, 'join'):
                                                        # 尝试join，但设置短超时
                                                        try:
                                                            process.join(timeout=0.1)
                                                        except:
                                                            pass
                                                except (OSError, ValueError, AttributeError):
                                                    # 进程可能已经退出
                                                    pass
                                            alive_processes = remaining_processes
                                            if alive_processes:
                                                time.sleep(0.1)  # 短暂休眠，避免CPU占用过高
                                        
                                        # 如果超时后仍有进程存活，强制终止
                                        if alive_processes:
                                            for process in alive_processes:
                                                _terminate_process_forcefully(process)
                                except Exception:
                                    # 如果正常关闭失败，强制关闭
                                    try:
                                        executor_to_clean.shutdown(wait=False)
                                    except:
                                        pass
                        except Exception:
                            # 如果关闭失败，尝试强制关闭
                            try:
                                executor_to_clean.shutdown(wait=False)
                            except:
                                pass
                        finally:
                            # 强制终止所有子进程（所有平台），确保没有孤儿进程
                            try:
                                if processes:
                                    # 第一轮：终止所有进程
                                    for process in processes:
                                        _terminate_process_forcefully(process)
                                    
                                    # 等待一段时间让进程退出
                                    time.sleep(0.3)
                                    
                                    # 第二轮：检查并强制终止仍在运行的进程
                                    for process in processes:
                                        try:
                                            if hasattr(process, 'is_alive') and process.is_alive():
                                                _terminate_process_forcefully(process)
                                        except (OSError, ValueError, AttributeError):
                                            # 进程可能已经退出
                                            pass
                                    
                                    # 第三轮：最后检查，确保所有进程都已退出（使用更短等待时间）
                                    time.sleep(0.2)
                                    for process in processes:
                                        try:
                                            if hasattr(process, 'is_alive') and process.is_alive():
                                                # 最后一次强制终止
                                                _terminate_process_forcefully(process)
                                        except (OSError, ValueError, AttributeError):
                                            # 进程可能已经退出
                                            pass
                            except Exception:
                                pass
                            
                            # 从活动列表中移除
                            try:
                                _active_executors_lock.acquire()
                                if executor_to_clean in _active_executors:
                                    _active_executors.remove(executor_to_clean)
                            finally:
                                _active_executors_lock.release()

            if result_texts:
                full_result_text = "\n".join(result_texts)
                full_result_text = f"处理完成！共处理 {total_files} 个文件\n" + full_result_text
            else:
                full_result_text = f"处理完成！共处理 {total_files} 个文件，但没有找到匹配项"

            self.result_signal.emit(full_result_text, all_results)
        except Exception as e:
            self.error_signal.emit(f"处理过程中出错: {str(e)}")
        finally:
            self.finished_signal.emit()

    def stop(self):
        """停止工作线程，并强制关闭进程池"""
        self.is_running = False
        # 如果进程池存在，强制关闭
        if self.executor:
            executor_to_clean = self.executor
            self.executor = None  # 先清空引用
            
            try:
                # 先获取所有子进程
                processes = _get_executor_processes(executor_to_clean)
                
                # 尝试取消所有未完成的任务
                try:
                    if sys.version_info >= (3, 9):
                        executor_to_clean.shutdown(wait=False, cancel_futures=True)
                    else:
                        executor_to_clean.shutdown(wait=False)
                except Exception:
                    try:
                        executor_to_clean.shutdown(wait=False)
                    except:
                        pass
                
                # 强制终止所有子进程（所有平台）
                if processes:
                    # 第一轮：终止所有进程
                    for process in processes:
                        _terminate_process_forcefully(process)
                    
                    # 等待子进程退出，但设置超时
                    max_wait_time = 3.0  # 最多等待3秒
                    start_time = time.time()
                    alive_processes = processes[:]
                    
                    # 轮询检查进程状态
                    while alive_processes and (time.time() - start_time) < max_wait_time:
                        remaining_processes = []
                        for process in alive_processes:
                            try:
                                if hasattr(process, 'is_alive') and process.is_alive():
                                    remaining_processes.append(process)
                                elif hasattr(process, 'join'):
                                    try:
                                        process.join(timeout=0.1)
                                    except:
                                        pass
                            except (OSError, ValueError, AttributeError):
                                # 进程可能已经退出
                                pass
                        alive_processes = remaining_processes
                        if alive_processes:
                            time.sleep(0.1)
                    
                    # 第二轮：再次检查并强制终止仍在运行的进程
                    time.sleep(0.3)
                    for process in processes:
                        try:
                            if hasattr(process, 'is_alive') and process.is_alive():
                                _terminate_process_forcefully(process)
                        except (OSError, ValueError, AttributeError):
                            # 进程可能已经退出
                            pass
                    
                    # 第三轮：最后检查，确保所有进程都已退出
                    time.sleep(0.2)
                    for process in processes:
                        try:
                            if hasattr(process, 'is_alive') and process.is_alive():
                                # 最后一次强制终止
                                _terminate_process_forcefully(process)
                        except (OSError, ValueError, AttributeError):
                            # 进程可能已经退出
                            pass
            except Exception:
                pass
            finally:
                # 从活动列表中移除
                try:
                    _active_executors_lock.acquire()
                    if executor_to_clean in _active_executors:
                        _active_executors.remove(executor_to_clean)
                finally:
                    _active_executors_lock.release()