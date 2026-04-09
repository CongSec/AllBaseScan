# -*- coding: utf-8 -*-
import json
import os
from constants import CONFIG_FILE_PATH

class ConfigManager:
    """配置管理类"""
    
    @staticmethod
    def load_config():
        """加载配置文件"""
        default_config = {
            "keywords": [],
            "nearby_lines": 2,
            "nearby_chars": 20,
            "down_lines": 0,
            "up_lines": 0,
            "auto_export": True,
            "auto_detect_encoding": True
        }
        
        if os.path.exists(CONFIG_FILE_PATH):
            try:
                with open(CONFIG_FILE_PATH, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    # 处理旧版本配置格式
                    for idx, kw in enumerate(config.get("keywords", [])):
                        if isinstance(kw, str):
                            config["keywords"][idx] = {
                                "words": [kw],
                                "exclude": [],
                                "enabled": True,
                                "down_lines": 0,
                                "up_lines": 0,
                                "exclude_nearby": True,
                                "multi_line_exclude": False,
                                "use_regex": False,
                                "remark": ""  # 添加备注字段默认值
                            }
                        elif isinstance(kw, dict):
                            if "word" in kw:
                                kw["words"] = [kw.pop("word")]
                            kw.setdefault("exclude", [])
                            kw.setdefault("enabled", True)
                            kw.setdefault("down_lines", 0)
                            kw.setdefault("up_lines", 0)
                            kw.setdefault("exclude_nearby", True)
                            kw.setdefault("multi_line_exclude", False)
                            kw.setdefault("use_regex", False)
                            kw.setdefault("remark", "")  # 为旧配置添加备注字段默认值
                    
                    # 确保所有默认配置项都存在
                    for key in default_config:
                        config.setdefault(key, default_config[key])
                    return config
            except Exception as e:
                print(f"读取配置文件出错: {e}，使用默认配置")
                return default_config.copy()
        else:
            # 创建默认配置文件
            with open(CONFIG_FILE_PATH, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, ensure_ascii=False, indent=4)
            return default_config.copy()
    
    @staticmethod
    def save_config(config):
        """保存配置文件"""
        with open(CONFIG_FILE_PATH, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
    
    @staticmethod
    def export_config(file_path):
        """导出配置文件到指定路径"""
        try:
            config = ConfigManager.load_config()
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=4)
            return True, None
        except Exception as e:
            return False, str(e)
    
    @staticmethod
    def import_config(file_path):
        """从指定路径导入配置文件"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                imported_config = json.load(f)
            
            # 验证配置格式
            if not isinstance(imported_config, dict):
                return False, "配置文件格式错误：根对象必须是字典"
            
            # 确保必要的字段存在
            default_config = {
                "keywords": [],
                "nearby_lines": 2,
                "nearby_chars": 20,
                "down_lines": 0,
                "up_lines": 0,
                "auto_export": True,
                "auto_detect_encoding": True
            }
            
            # 合并默认配置，确保所有字段都存在
            for key in default_config:
                if key not in imported_config:
                    imported_config[key] = default_config[key]
            
            # 验证和修复关键字格式
            if "keywords" in imported_config:
                if not isinstance(imported_config["keywords"], list):
                    return False, "配置文件格式错误：keywords 必须是数组"
                
                # 处理旧版本配置格式
                for idx, kw in enumerate(imported_config["keywords"]):
                    if isinstance(kw, str):
                        imported_config["keywords"][idx] = {
                            "words": [kw],
                            "exclude": [],
                            "enabled": True,
                            "down_lines": 0,
                            "up_lines": 0,
                            "exclude_nearby": True,
                            "multi_line_exclude": False,
                            "use_regex": False,
                            "remark": ""
                        }
                    elif isinstance(kw, dict):
                        if "word" in kw:
                            kw["words"] = [kw.pop("word")]
                        kw.setdefault("exclude", [])
                        kw.setdefault("enabled", True)
                        kw.setdefault("down_lines", 0)
                        kw.setdefault("up_lines", 0)
                        kw.setdefault("exclude_nearby", True)
                        kw.setdefault("multi_line_exclude", False)
                        kw.setdefault("use_regex", False)
                        kw.setdefault("remark", "")
            
            # 保存导入的配置
            ConfigManager.save_config(imported_config)
            return True, imported_config
        except json.JSONDecodeError as e:
            return False, f"JSON解析错误：{str(e)}"
        except Exception as e:
            return False, f"导入配置文件失败：{str(e)}"