"""LLM Judge module for evaluating agent session trajectories."""

import json
import logging
import os
import re
from datetime import datetime
from typing import Optional, Callable, List, Dict

import httpx
import yaml


logger = logging.getLogger(__name__)

JUDGE_SYSTEM_PROMPT = """You are a session analyst for an AI coding agent. Given a session trajectory (user messages + assistant actions), evaluate:

1. Did the agent succeed at the user's task? (success: true/false)
2. What was the primary task goal? (task_goal: string)
3. What was the critical bottleneck or key insight? (critical_bottleneck: string)
4. What domain does this task belong to? Pick from: debugging, api-design, testing, configuration, research, refactoring, planning, general

Output ONLY valid JSON matching:
{"success": bool, "task_goal": "string", "critical_bottleneck": "string", "domain": "string"}"""


def _openrouter_model(model_name: str) -> str:
    """Add OpenRouter provider prefix if model name lacks one."""
    if "/" in model_name:
        return model_name
    known = {
        "deepseek": "deepseek",
        "gpt": "openai",
        "o1": "openai",
        "o3": "openai",
        "o4": "openai",
        "gemini": "google",
        "claude": "anthropic",
        "llama": "meta-llama",
        "mistral": "mistralai",
        "mixtral": "mistralai",
        "qwen": "qwen",
        "nemotron": "nvidia",
    }
    for prefix, provider in known.items():
        if model_name.lower().startswith(prefix):
            return f"{provider}/{model_name}"
    return model_name


def judge_session(trajectory_text: str, llm_call_fn: Callable[[str, str], str]) -> dict:
    """
    Judge whether an agent session was successful.

    Args:
        trajectory_text: The session trajectory text to analyze.
        llm_call_fn: A callable that takes (prompt, system_prompt) and returns LLM response.

    Returns:
        Dict with keys: success, task_goal, critical_bottleneck, domain.
        On failure, returns default values with success as None.
    """
    default_result = {
        "success": None,
        "task_goal": "",
        "critical_bottleneck": "",
        "domain": "general",
    }

    try:
        response = llm_call_fn(trajectory_text, JUDGE_SYSTEM_PROMPT)

        parsed = json.loads(response)

        required_keys = ["success", "task_goal", "critical_bottleneck", "domain"]
        for key in required_keys:
            if key not in parsed:
                logger.warning(f"Missing key '{key}' in LLM response")
                return default_result

        return {
            "success": parsed.get("success"),
            "task_goal": parsed.get("task_goal", ""),
            "critical_bottleneck": parsed.get("critical_bottleneck", ""),
            "domain": parsed.get("domain", "general"),
        }

    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse JSON from LLM response: {e}")
        return default_result
    except Exception as e:
        logger.warning(f"Error in judge_session: {e}")
        return default_result


def build_llm_call_fn(
    mempalace_config: Optional[dict] = None,
    provider_override: Optional[str] = None,
    model_override: Optional[str] = None,
) -> Optional[Callable]:
    """
    Build a callable that makes OpenAI-compatible API calls using Hermes config.

    Reads ~/.hermes/config.yaml and ~/.hermes/.env for model configuration.

    Args:
        mempalace_config: Optional config dict (currently unused, reserved for future).
        provider_override: If set, use only this provider (e.g. 'generativelanguage.googleapis.com').
        model_override: If set, use this model name instead of auto-detected.

    Returns:
        A callable llm_call_fn(prompt: str, system_prompt: str) -> str,
        or None if config cannot be read.
    """
    try:
        config_path = os.path.expanduser("~/.hermes/config.yaml")
        env_path = os.path.expanduser("~/.hermes/.env")

        base_url = None
        api_key = None
        model_name = None

        # Step 1: Read Hermes config.yaml for model/base_url/model_name
        hermes_config = None
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                hermes_config = yaml.safe_load(f) or {}
            model_config = hermes_config.get("model", {})
            base_url = model_config.get("base_url")
            model_name = model_config.get("default") or model_config.get("model")

        # Step 1.5: If provider_override is set, try that specific provider
        placeholder_re = r"^(random-|sk-placeholder|[*]{3})"
        if provider_override and hermes_config:
            providers = hermes_config.get("providers", {})
            pcfg = providers.get(provider_override)
            if pcfg:
                pkey = (pcfg.get("api_key") or "").strip()
                if pkey and not re.match(placeholder_re, pkey):
                    api_key = pkey
                    base_url = pcfg.get("api", pcfg.get("api_url", ""))
                    p_model = pcfg.get("default_model", "")
                    if p_model:
                        model_name = p_model
                    logger.info(
                        "Using provider '%s' (overridden) for reasoning bank",
                        provider_override,
                    )

        # Step 2: Scan all configured providers for one with a real
        # (non-placeholder) API key. Skip if provider_override already found one.
        if not api_key and hermes_config:
            providers = hermes_config.get("providers", {})
            for pname, pcfg in providers.items():
                pkey = (pcfg.get("api_key") or "").strip()
                if pkey and not re.match(placeholder_re, pkey):
                    api_key = pkey
                    base_url = pcfg.get("api", pcfg.get("api_url", ""))
                    p_model = pcfg.get("default_model", "")
                    if p_model:
                        model_name = p_model
                    logger.info(
                        "Using provider '%s' for reasoning bank LLM calls",
                        pname,
                    )
                    break

        # Step 3: Check .env for OpenRouter or other keys (fallback
        # if no provider has a real key)
        if not api_key and os.path.exists(env_path):
            with open(env_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        key = key.strip()
                        value = value.strip()
                        if key == "OPENROUTER_API_KEY" and value and value != "***":
                            api_key = value
                            base_url = "https://openrouter.ai/api/v1"
                        elif key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY") and value:
                            if not api_key:
                                api_key = value

        # Apply model_override if set (takes precedence over auto-detected)
        if model_override:
            model_name = model_override
            logger.info("Using model '%s' (overridden) for reasoning bank", model_name)

        if not base_url or not api_key or not model_name:
            logger.warning(
                "Incomplete config: missing base_url, api_key, or model_name"
            )
            return None

        def llm_call_fn(prompt: str, system_prompt: str) -> str:
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            # Add OpenRouter-specific headers if using OpenRouter
            if "openrouter" in (base_url or ""):
                headers["HTTP-Referer"] = "https://github.com/NehuenD/hermes_mempalace"
                headers["X-Title"] = "MemPalace ReasoningBank"
                effective_model = _openrouter_model(model_name)
            else:
                effective_model = model_name
            payload = {
                "model": effective_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.3,
                "max_tokens": 500,
            }

            response = httpx.post(
                f"{base_url}/chat/completions",
                json=payload,
                headers=headers,
                timeout=30.0,
            )
            if response.status_code != 200:
                logger.warning(f"LLM API returned status {response.status_code}")
                return "{}"
            data = response.json()
            return data["choices"][0]["message"]["content"]

        return llm_call_fn

    except FileNotFoundError:
        logger.warning("Hermes config file not found")
        return None
    except yaml.YAMLError as e:
        logger.warning(f"Failed to parse YAML config: {e}")
        return None
    except Exception as e:
        logger.warning(f"Error building LLM call function: {e}")
        return None


def condense_trajectory(messages: List[Dict], max_last_n: int = 10) -> str:
    """
    Condense a list of messages into a summary string.

    Takes the last max_last_n messages and formats each as "[role]: content[:500]".

    Args:
        messages: List of message dicts with 'role' and 'content' keys.
        max_last_n: Maximum number of recent messages to include.

    Returns:
        Condensed trajectory string with newlines between messages.
    """
    recent = messages[-max_last_n:] if len(messages) > max_last_n else messages

    lines = []
    for msg in recent:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        if len(content) > 500:
            content = content[:500] + "..."
        lines.append(f"[{role}]: {content}")

    return "\n".join(lines)
