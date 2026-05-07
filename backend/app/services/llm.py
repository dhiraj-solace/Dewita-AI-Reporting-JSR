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


async def generate_sql_with_ai(
    question: str,
    start_date: str | None,
    end_date: str | None,
    similar_examples: list[dict[str, str]] | None = None,
    mistake_examples: list[dict[str, str]] | None = None,
    provider: str | None = None,
) -> dict[str, Any] | None:
    extra = None
    if similar_examples or mistake_examples:
        extra = {
            "requirements": [
                "Use correct_approved_examples only as reference patterns.",
                "Do not copy an example SQL blindly; the current question, schema catalog, and safety rules are authoritative.",
                "Do not repeat mistakes shown in past_mistakes_to_avoid. Use them only as warnings.",
            ],
        }
        if similar_examples:
            extra["correct_approved_examples"] = _format_correct_examples(similar_examples)
        if mistake_examples:
            extra["past_mistakes_to_avoid"] = _format_mistake_examples(mistake_examples)
    payload = _build_sql_payload(question, start_date, end_date, extra)
    return await _generate_sql_payload(payload, question=question, provider=provider)


def build_sql_generation_payload_preview(
    question: str,
    start_date: str | None,
    end_date: str | None,
    similar_examples: list[dict[str, str]] | None = None,
    mistake_examples: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    extra = None
    if similar_examples or mistake_examples:
        extra = {
            "requirements": [
                "Use correct_approved_examples only as reference patterns.",
                "Do not copy an example SQL blindly; the current question, schema catalog, and safety rules are authoritative.",
                "Do not repeat mistakes shown in past_mistakes_to_avoid. Use them only as warnings.",
            ],
        }
        if similar_examples:
            extra["correct_approved_examples"] = _format_correct_examples(similar_examples)
        if mistake_examples:
            extra["past_mistakes_to_avoid"] = _format_mistake_examples(mistake_examples)
    payload = json.loads(_build_sql_payload(question, start_date, end_date, extra))
    examples = payload.get("correct_approved_examples") or []
    mistakes = payload.get("past_mistakes_to_avoid") or []
    return {
        "question": payload.get("question"),
        "start_date": payload.get("start_date"),
        "end_date": payload.get("end_date"),
        "requirements_count": len(payload.get("requirements") or []),
        "similar_examples_count": len(examples),
        "mistake_examples_count": len(mistakes),
        "similar_examples_preview": [
            {
                "user_question": _short_text(str(example.get("user_question") or ""), 120),
                "correct_sql": _short_text(str(example.get("correct_sql") or ""), 220),
            }
            for example in examples[:3]
        ],
        "mistake_examples_preview": [
            {
                "user_question": _short_text(str(example.get("user_question") or ""), 120),
                "wrong_sql": _short_text(str(example.get("wrong_sql") or ""), 180),
                "reason": _short_text(str(example.get("reason") or ""), 160),
                "correct_sql": _short_text(str(example.get("correct_sql") or ""), 180),
            }
            for example in mistakes[:3]
        ],
    }


async def generate_sql_repair_with_ai(
    question: str,
    start_date: str | None,
    end_date: str | None,
    failed_sql: str,
    error_message: str,
    provider: str | None = None,
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
    return await _generate_sql_payload(payload, question=question, provider=provider)


def _format_correct_examples(examples: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {
            "label": "Correct approved example",
            "user_question": example.get("user_question", ""),
            "correct_sql": example.get("sql") or example.get("correct_sql", ""),
        }
        for example in examples[:3]
    ]


def _format_mistake_examples(examples: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {
            "label": "Past mistake to avoid",
            "user_question": example.get("user_question", ""),
            "wrong_sql": example.get("wrong_sql", ""),
            "reason_it_was_wrong": example.get("reason", ""),
            "correct_sql": example.get("correct_sql", ""),
            "instruction": "Do not repeat this mistake. Use it only as warning/context.",
        }
        for example in examples[:3]
        if example.get("reason") or example.get("correct_sql")
    ]


async def generate_sql_validation_retry_with_ai(
    question: str,
    start_date: str | None,
    end_date: str | None,
    failed_output: dict[str, Any],
    validation_errors: list[dict[str, Any]],
    retry_prompt: str,
    provider: str | None = None,
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
                "Do not return clarification_needed when the issue is only a missing top/limit count; use the safe app LIMIT instead.",
            ],
        },
    )
    return await _generate_sql_payload(payload, question=question, provider=provider)


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
            "If the question says top, highest, best, most, or leading without a number, rank the results and use the safe app LIMIT.",
            "If no count is requested, include a safe LIMIT based on the app request limit.",
            "Prefer documented tables and columns.",
            "Only SELECT or WITH queries are allowed.",
            "Never generate INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, CREATE, GRANT, EXEC, CALL, or multiple statements.",
            "If the question is unclear, return clarification_needed instead of SQL.",
        ],
    }
    if extra:
        extra_requirements = extra.pop("requirements", None)
        payload.update(extra)
        if isinstance(extra_requirements, list):
            payload["requirements"].extend(extra_requirements)
    return json.dumps(payload)


async def _generate_sql_payload(
    payload: str,
    question: str | None = None,
    provider: str | None = None,
) -> dict[str, Any] | None:
    settings = get_settings()
    if not settings.ai_sql_enabled:
        logger.warning("AI SQL generation is disabled in settings")
        return None
    
    prompt = (Path(__file__).resolve().parents[1] / "prompts" / "sql_system.md").read_text(encoding="utf-8")

    provider = (provider or settings.ai_provider).lower()
    context = catalog_context()

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
            context,
        )

    if provider == "ollama":
        logger.info(f"Using Ollama SQL provider with model: {settings.ollama_sql_model}")
        return await _generate_sql_with_ollama(
            prompt,
            payload,
            settings.ollama_sql_url,
            settings.ollama_sql_model,
            settings.ollama_sql_timeout_seconds,
            context,
        )

    if provider == "gemini":
        if not settings.gemini_api_key:
            raise AiSqlGenerationError(
                "Gemini API key is not configured.",
                title="AI provider is not configured",
                solution="Add GEMINI_API_KEY in the backend .env file, or switch AI_PROVIDER to a configured provider.",
            )
        logger.info(f"Using Gemini AI provider with model: {settings.gemini_model}")
        return await _generate_sql_with_gemini(prompt, payload, settings.gemini_api_key, settings.gemini_model, context)

    if not settings.openai_api_key:
        raise AiSqlGenerationError(
            "OpenAI API key is not configured.",
            title="AI provider is not configured",
            solution="Add OPENAI_API_KEY in the backend .env file, or switch AI_PROVIDER to a configured provider.",
        )
    logger.info(f"Using OpenAI AI provider with model: {settings.openai_model}")
    return await _generate_sql_with_openai(prompt, payload, settings.openai_api_key, settings.openai_model, context)


async def _generate_sql_with_openrouter(
    prompt: str,
    payload: str,
    api_key: str,
    model: str,
    site_url: str | None,
    app_name: str,
    context: str,
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
            {"role": "user", "content": context},
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

async def _generate_sql_with_ollama(
    prompt: str,
    payload: str,
    url: str,
    model: str,
    timeout_seconds: float,
    context: str,
) -> dict[str, Any] | None:
    body = {
        "model": model,
        "stream": False,
        "options": {"temperature": 0, "top_p": 1, "top_k": 1, "num_ctx": 8192},
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": context},
            {"role": "user", "content": payload},
        ],
    }
    try:
        timeout = httpx.Timeout(timeout_seconds, connect=10)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=body)
            response.raise_for_status()
        content = response.json().get("message", {}).get("content", "") or ""
        return _parse_ai_sql(content)
    except httpx.HTTPError as e:
        raise AiSqlGenerationError(
            f"Ollama SQL generation failed: {_http_error_message(e)}",
            title="Local Qwen request failed",
            solution="Local Qwen is using the full database schema and may take several minutes. Try again, increase OLLAMA_SQL_TIMEOUT_SECONDS, or switch SQL generation to OpenRouter for faster response.",
        ) from e
    except Exception as e:
        logger.error(f"Ollama SQL generation failed: {str(e)}")
        raise AiSqlGenerationError(
            f"Ollama SQL generation failed: {str(e)}",
            title="Local Qwen request failed",
            solution="Ensure Ollama is running and qwen2.5:3b is installed. If it is running, switch SQL generation to OpenRouter or increase OLLAMA_SQL_TIMEOUT_SECONDS for full-schema local generation.",
        ) from e


async def _generate_sql_with_openai(prompt: str, payload: str, api_key: str, model: str, context: str) -> dict[str, Any] | None:
    from openai import AsyncOpenAI
    
    try:
        logger.info("Calling OpenAI API for SQL generation")
        client = AsyncOpenAI(api_key=api_key)
        response = await client.chat.completions.create(
            model=model,
            temperature=0,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": context},
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


async def _generate_sql_with_gemini(prompt: str, payload: str, api_key: str, model: str, context: str) -> dict[str, Any] | None:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body = {
        "systemInstruction": {"parts": [{"text": prompt}]},
        "contents": [
            {
                "role": "user",
                "parts": [{"text": context}],
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


def _short_text(value: str, max_length: int) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= max_length:
        return normalized
    return normalized[: max_length - 1].rstrip() + "."


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


def _http_error_message(exc: httpx.HTTPError) -> str:
    if isinstance(exc, httpx.TimeoutException):
        return "timed out waiting for local model response"
    if isinstance(exc, httpx.ConnectError):
        return "could not connect to Ollama"
    if isinstance(exc, httpx.HTTPStatusError):
        return f"Ollama returned HTTP {exc.response.status_code}"
    return exc.__class__.__name__
