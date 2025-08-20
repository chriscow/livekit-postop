"""
YAML-based prompt management for PostOp AI system
"""
import os
import yaml
from pathlib import Path
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)

class PromptManager:
    """Manages external prompt templates with YAML loading and caching"""
    
    def __init__(self, prompts_dir: str = "../prompts"):
        # Get the directory relative to this file's location
        current_dir = Path(__file__).parent
        self.prompts_dir = current_dir / prompts_dir
        self._prompts_cache = {}
    
    def load_prompt(self, prompt_name: str, **kwargs) -> str:
        """Load and format prompt from YAML file"""
        if prompt_name not in self._prompts_cache:
            prompt_file = self.prompts_dir / f"{prompt_name}.yaml"
            
            if not prompt_file.exists():
                logger.warning(f"Prompt file not found: {prompt_file}. Using fallback.")
                raise FileNotFoundError(f"Prompt file {prompt_file} does not exist.")
            
            try:
                with open(prompt_file, 'r', encoding='utf-8') as f:
                    prompt_data = yaml.safe_load(f)
                    self._prompts_cache[prompt_name] = prompt_data
                    logger.info(f"Loaded prompt template: {prompt_name}")
            except Exception as e:
                logger.error(f"Failed to load prompt {prompt_name}: {e}")
                raise FileNotFoundError(f"Prompt file {prompt_file} does not exist.")

        prompt_data = self._prompts_cache[prompt_name]
        template = prompt_data.get('template', '')
        
        try:
            return template.format(**kwargs)
        except KeyError as e:
            logger.error(f"Missing template variable in {prompt_name}: {e}")
            raise ValueError(f"Missing template variable: {e}")
    
    def reload_prompts(self):
        """Reload all cached prompts (useful for development)"""
        self._prompts_cache.clear()
        logger.info("Prompt cache cleared - prompts will be reloaded")
    
    def get_prompt_info(self, prompt_name: str) -> Dict[str, Any]:
        """Get prompt metadata (description, version, etc.)"""
        prompt_file = self.prompts_dir / f"{prompt_name}.yaml"
        
        if not prompt_file.exists():
            return {"error": f"Prompt file not found: {prompt_file}"}
        
        try:
            with open(prompt_file, 'r', encoding='utf-8') as f:
                prompt_data = yaml.safe_load(f)
                return {
                    "description": prompt_data.get("description", "No description available"),
                    "version": prompt_data.get("version", "Unknown"),
                    "file": str(prompt_file),
                    "template_length": len(prompt_data.get("template", ""))
                }
        except Exception as e:
            return {"error": f"Failed to read prompt metadata: {e}"}

# Global prompt manager instance
prompt_manager = PromptManager()