"""子Agent 配置加载器。"""

import yaml
from pathlib import Path
from typing import List, Dict, Any

from app.tools import TOOL_GROUPS, SUBAGENT_TOOLS
from app.log_utils import get_logger
from app.llm_config import create_chat_model

logger = get_logger("loader")


class SubAgentLoader:
    """子Agent YAML 配置加载器"""

    def __init__(self, config_dir: str):
        self.config_dir = Path(config_dir)
        logger.info("loader_initialized", config_dir=str(self.config_dir))

    def load_all(self) -> List[Dict[str, Any]]:
        """加载所有启用的子Agent配置"""
        logger.info("loading_subagents", config_dir=str(self.config_dir))

        if not self.config_dir.exists():
            logger.warning("config_dir_not_found", config_dir=str(self.config_dir))
            return []

        yaml_files = list(self.config_dir.glob("*.yaml"))
        logger.info("found_yaml_files", count=len(yaml_files), files=[f.name for f in yaml_files])

        subagents = []
        for yaml_file in yaml_files:
            logger.info("loading_yaml_file", file=yaml_file.name)

            with open(yaml_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)

            if not config.get('enabled', True):
                logger.info("subagent_disabled", name=config.get("name", yaml_file.stem))
                continue

            subagent_name = config["name"]
            subagent = {
                "name": subagent_name,
                "description": config.get("description", ""),
                "system_prompt": config.get("system_prompt", ""),
            }
            logger.info("subagent_parsed",
                        name=subagent["name"],
                        has_description=bool(subagent["description"]),
                        has_system_prompt=bool(subagent["system_prompt"]))

            # 模型配置
            if config.get("model"):
                model_name = config["model"]
                logger.info("subagent_model_set", name=subagent["name"], model=model_name)
                model_instance = create_chat_model(model_name)
                subagent["model"] = model_instance

            # 工具配置解析
            tools_cfg = config.get("tools")
            if tools_cfg:
                logger.info("loading_tools", subagent=subagent["name"], tools_config=tools_cfg)

                # 收集所有工具
                all_tools = []
                for group in TOOL_GROUPS.values():
                    all_tools.extend(group)
                tool_name_map = {t.name: t for t in all_tools}

                if isinstance(tools_cfg, str):
                    # 按分组名加载
                    tools = TOOL_GROUPS.get(tools_cfg, [])
                    logger.info("tools_by_group",
                                subagent=subagent["name"],
                                group=tools_cfg,
                                tool_count=len(tools))
                elif isinstance(tools_cfg, list):
                    # 精确工具名列表
                    tools = [tool_name_map[name] for name in tools_cfg if name in tool_name_map]
                    logger.info("tools_by_list",
                                subagent=subagent["name"],
                                requested_tools=tools_cfg,
                                loaded_count=len(tools))
                else:
                    # 使用预配置的工具分组
                    tools = SUBAGENT_TOOLS.get(subagent_name, [])
                    logger.info("tools_by_subagent_default",
                                subagent=subagent["name"],
                                tool_count=len(tools))

                if tools:
                    subagent["tools"] = tools
                    logger.info("subagent_tools_set",
                                subagent=subagent["name"],
                                tool_names=[t.name for t in tools])

            # 技能目录配置
            skills_dirs = config.get("skills")
            if skills_dirs:
                subagent["skills"] = skills_dirs
                logger.info("subagent_skills_set",
                            subagent=subagent["name"],
                            skills=skills_dirs)

            # 超时配置
            if config.get("timeout_seconds"):
                subagent["timeout_seconds"] = config["timeout_seconds"]

            subagents.append(subagent)
            logger.info("subagent_loaded", name=subagent["name"])

        logger.info("all_subagents_loaded", count=len(subagents))
        return subagents