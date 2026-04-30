import json
import logging
from pathlib import Path
from typing import Any
import httpx
from app.core.config import get_settings
from app.services.catalog import catalog_context

logger = logging.getLogger(__name__)

async def generate_sql_with_ai(question: str, start_date: str | None, end_date: str | None) -> dict[str, Any] | None:
    settings = get_settings()
    if not settings.ai_sql_enabled:
        logger.warning("AI SQL generation is disabled in settings")
        return None
    
    prompt = (Path(__file__).resolve().parents[1] / "prompts" / "sql_system.md").read_text(encoding="utf-8")
    payload = json.dumps(
        {
            "question": question,
            "start_date": start_date,
            "end_date": end_date,
            "requirements": [
                "Return one MySQL SELECT query only.",
                "Use :start_date and :end_date parameters when date filtering is needed.",
                "Prefer documented tables and columns.",
            ],
        }
    )

    provider = settings.ai_provider.lower()

    if provider == "openrouter":
        if not settings.openrouter_api_key:
            logger.error("OpenRouter API key not configured")
            return None
        logger.info(f"Using OpenRouter provider with model: {settings.openrouter_model}")
        return await _generate_sql_with_openrouter(
            prompt,
            payload,
            settings.openrouter_api_key,
            settings.openrouter_model,
            settings.openrouter_site_url,
            settings.openrouter_app_name,
        )

    if provider == "gemini":
        if not settings.gemini_api_key:
            logger.error("Gemini API key not configured")
            return None
        logger.info(f"Using Gemini AI provider with model: {settings.gemini_model}")
        return await _generate_sql_with_gemini(prompt, payload, settings.gemini_api_key, settings.gemini_model)

    if not settings.openai_api_key:
        logger.error("OpenAI API key not configured")
        return None
    logger.info(f"Using OpenAI AI provider with model: {settings.openai_model}")
    return await _generate_sql_with_openai(prompt, payload, settings.openai_api_key, settings.openai_model)


async def _generate_sql_with_openrouter(
    prompt: str,
    payload: str,
    api_key: str,
    model: str,
    site_url: str | None,
    app_name: str,
) -> dict[str, Any] | None:
    headers = {"Authorization": f"Bearer {api_key}"}
    if site_url:
        headers["HTTP-Referer"] = site_url
    if app_name:
        headers["X-Title"] = app_name

    body = {
        "model": model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": catalog_context()},
            {"role": "user", "content": payload},
        ],
    }
    try:
        logger.info("Calling OpenRouter API for SQL generation")
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=body,
            )
            response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"] or "{}"
        logger.info("OpenRouter API call successful")
        return _parse_ai_json(content)
    except Exception as e:
        logger.error(f"OpenRouter API call failed: {str(e)}")
        return None

async def _generate_sql_with_openai(prompt: str, payload: str, api_key: str, model: str) -> dict[str, Any] | None:
    from openai import AsyncOpenAI
    
    try:
        logger.info("Calling OpenAI API for SQL generation")
        client = AsyncOpenAI(api_key=api_key)
        response = await client.chat.completions.create(
            model=model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": catalog_context()},
                {"role": "user", "content": payload},
            ],
        )
        content = response.choices[0].message.content or "{}"
        logger.info("OpenAI API call successful")
        return _parse_ai_json(content)
    except Exception as e:
        logger.error(f"OpenAI API call failed: {str(e)}")
        return None


async def _generate_sql_with_gemini(prompt: str, payload: str, api_key: str, model: str) -> dict[str, Any] | None:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body = {
        "systemInstruction": {"parts": [{"text": prompt}]},
        "contents": [
            {
                "role": "user",
                "parts": [{"text": catalog_context()}],
            },
            {
                "role": "user",
                "parts": [{"text": payload}],
            },
        ],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
        },
    }
    try:
        logger.info("Calling Gemini API for SQL generation")
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(url, params={"key": api_key}, json=body)
            response.raise_for_status()
        data = response.json()
        content = data["candidates"][0]["content"]["parts"][0]["text"]
        logger.info("Gemini API call successful")
        return _parse_ai_json(content)
    except Exception as e:
        logger.error(f"Gemini API call failed: {str(e)}")
        return None


def _parse_ai_json(content: str) -> dict[str, Any]:
    parsed = json.loads(content)
    return {
        "title": parsed.get("title") or "Custom Report",
        "sql": parsed["sql"],
        "explanation": parsed.get("explanation") or "Generated from the semantic catalog.",
        "assumptions": parsed.get("assumptions") or [],
    }
