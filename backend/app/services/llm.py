import json
import logging
from pathlib import Path
from typing import Any
import httpx
from app.core.config import get_settings
from app.services.catalog import catalog_context

logger = logging.getLogger(__name__)


class AiSqlGenerationError(Exception):
    def __init__(
        self,
        message: str,
        title: str = "AI SQL generation failed",
        solution: str | None = None,
        status_code: int | None = None,
    ):
        super().__init__(message)
        self.title = title
        self.solution = solution
        self.status_code = status_code


async def generate_sql_with_ai(question: str, start_date: str | None, end_date: str | None) -> dict[str, Any] | None:
    payload = _build_sql_payload(question, start_date, end_date)
    return await _generate_sql_payload(payload)


async def generate_sql_repair_with_ai(
    question: str,
    start_date: str | None,
    end_date: str | None,
    failed_sql: str,
    error_message: str,
) -> dict[str, Any] | None:
    payload = _build_sql_payload(
        question,
        start_date,
        end_date,
        {
            "repair_mode": True,
            "failed_sql": failed_sql,
            "error_message": error_message,
            "requirements": [
                "Generate a corrected replacement query.",
                "Do not repeat the same invalid table or column reference.",
                "Use the supplied schema catalog and error_message to choose valid tables, columns, aliases, and joins.",
                "If error_message names a missing column, find the correct column/table in the schema catalog before rewriting.",
            ],
        },
    )
    return await _generate_sql_payload(payload)


async def generate_sql_validation_retry_with_ai(
    question: str,
    start_date: str | None,
    end_date: str | None,
    failed_output: dict[str, Any],
    validation_errors: list[dict[str, Any]],
    retry_prompt: str,
) -> dict[str, Any] | None:
    payload = _build_sql_payload(
        question,
        start_date,
        end_date,
        {
            "validation_retry_mode": True,
            "failed_sql": failed_output.get("sql") if isinstance(failed_output, dict) else failed_output,
            "validation_errors": validation_errors,
            "validator_retry_prompt": retry_prompt,
            "requirements": [
                "Regenerate only the corrected SQL query.",
                "Correct every validation error before returning.",
                "Do not repeat unsafe SQL or invalid schema references.",
            ],
        },
    )
    return await _generate_sql_payload(payload)


def _build_sql_payload(
    question: str,
    start_date: str | None,
    end_date: str | None,
    extra: dict[str, Any] | None = None,
) -> str:
    payload: dict[str, Any] = {
        "question": question,
        "start_date": start_date,
        "end_date": end_date,
        "requirements": [
            "Return one MySQL SELECT query only as plain text.",
            "Do not return JSON, markdown, explanation, assumptions, comments, or metadata.",
            "Use literal MySQL date values from start_date and end_date when date filtering is needed, not placeholders.",
            "Include the requested top/limit count when the question asks for one.",
            "If no count is requested, include a safe LIMIT based on the app request limit.",
            "Prefer documented tables and columns.",
        ],
    }
    if extra:
        extra_requirements = extra.pop("requirements", None)
        payload.update(extra)
        if isinstance(extra_requirements, list):
            payload["requirements"].extend(extra_requirements)
    return json.dumps(payload)


async def _generate_sql_payload(payload: str) -> dict[str, Any] | None:
    settings = get_settings()
    if not settings.ai_sql_enabled:
        logger.warning("AI SQL generation is disabled in settings")
        return None
    
    prompt = (Path(__file__).resolve().parents[1] / "prompts" / "sql_system.md").read_text(encoding="utf-8")

    provider = settings.ai_provider.lower()

    if provider == "openrouter":
        if not settings.openrouter_api_key:
            raise AiSqlGenerationError(
                "OpenRouter API key is not configured.",
                title="AI provider is not configured",
                solution="Add OPENROUTER_API_KEY in the backend .env file, or disable AI SQL generation to use built-in templates only.",
            )
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
            raise AiSqlGenerationError(
                "Gemini API key is not configured.",
                title="AI provider is not configured",
                solution="Add GEMINI_API_KEY in the backend .env file, or switch AI_PROVIDER to a configured provider.",
            )
        logger.info(f"Using Gemini AI provider with model: {settings.gemini_model}")
        return await _generate_sql_with_gemini(prompt, payload, settings.gemini_api_key, settings.gemini_model)

    if not settings.openai_api_key:
        raise AiSqlGenerationError(
            "OpenAI API key is not configured.",
            title="AI provider is not configured",
            solution="Add OPENAI_API_KEY in the backend .env file, or switch AI_PROVIDER to a configured provider.",
        )
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
        return _parse_ai_sql(content)
    except httpx.HTTPStatusError as e:
        raise _provider_http_error("OpenRouter", e) from e
    except Exception as e:
        logger.error(f"OpenRouter API call failed: {str(e)}")
        raise AiSqlGenerationError(
            f"OpenRouter API call failed: {str(e)}",
            title="OpenRouter request failed",
            solution="Check the OpenRouter API key, model name, provider status, and backend network access.",
        ) from e

async def _generate_sql_with_openai(prompt: str, payload: str, api_key: str, model: str) -> dict[str, Any] | None:
    from openai import AsyncOpenAI
    
    try:
        logger.info("Calling OpenAI API for SQL generation")
        client = AsyncOpenAI(api_key=api_key)
        response = await client.chat.completions.create(
            model=model,
            temperature=0,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": catalog_context()},
                {"role": "user", "content": payload},
            ],
        )
        content = response.choices[0].message.content or "{}"
        logger.info("OpenAI API call successful")
        return _parse_ai_sql(content)
    except Exception as e:
        logger.error(f"OpenAI API call failed: {str(e)}")
        status_code = getattr(e, "status_code", None)
        if status_code == 429:
            raise AiSqlGenerationError(
                "OpenAI rate limit was reached.",
                title="AI provider rate limit reached",
                solution="Wait a moment and retry, reduce report generation frequency, or use a provider/model with more available quota.",
                status_code=status_code,
            ) from e
        raise AiSqlGenerationError(
            f"OpenAI API call failed: {str(e)}",
            title="OpenAI request failed",
            solution="Check the OpenAI API key, model name, provider status, and backend network access.",
            status_code=status_code,
        ) from e


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
        return _parse_ai_sql(content)
    except httpx.HTTPStatusError as e:
        raise _provider_http_error("Gemini", e) from e
    except Exception as e:
        logger.error(f"Gemini API call failed: {str(e)}")
        raise AiSqlGenerationError(
            f"Gemini API call failed: {str(e)}",
            title="Gemini request failed",
            solution="Check the Gemini API key, model name, provider status, and backend network access.",
        ) from e


def _parse_ai_sql(content: str) -> dict[str, Any]:
    raw = content.strip()
    if raw.startswith("```"):
        raw = raw.strip("`").strip()
        raw = raw.removeprefix("sql").strip()
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict) and isinstance(parsed.get("sql"), str):
            raw = parsed["sql"].strip()
    except json.JSONDecodeError:
        pass
    return {"sql": raw.strip().rstrip(";")}


def _provider_http_error(provider: str, error: httpx.HTTPStatusError) -> AiSqlGenerationError:
    status_code = error.response.status_code
    logger.error(f"{provider} API call failed: {str(error)}")
    if status_code == 429:
        return AiSqlGenerationError(
            f"{provider} rate limit was reached.",
            title="AI provider rate limit reached",
            solution="Wait a moment and retry, reduce report generation frequency, or switch to a provider/model with more available quota.",
            status_code=status_code,
        )
    return AiSqlGenerationError(
        f"{provider} API returned HTTP {status_code}.",
        title=f"{provider} request failed",
        solution="Check provider quota, API key permissions, selected model availability, and provider status.",
        status_code=status_code,
    )
