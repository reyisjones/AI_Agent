"""
Agent core — orchestration loop using the OpenAI Responses API.

Key design choices:
- Uses client.responses.create() (not the deprecated Assistants API).
- previous_response_id enables multi-turn continuity without re-sending
  the full history on every turn.
- Tool calls are executed by the tool registry and fed back via
  a "function_call_output" input item.
- Retries with exponential backoff for transient OpenAI errors.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import openai
from openai import AsyncOpenAI
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.agent.prompts import SYSTEM_PROMPT
from app.config import get_settings
from app.memory import short_term
from app.observability.telemetry import get_tracer
from app.tools.registry import TOOLS_SCHEMAS, dispatch

logger = logging.getLogger(__name__)
tracer = get_tracer("agent.core")

_MAX_TOOL_ROUNDS = 10  # guard against infinite tool loops


# ── Retry decorator for transient OpenAI errors ──────────────────────────────

def _is_transient(exc: BaseException) -> bool:
    return isinstance(
        exc,
        (
            openai.APITimeoutError,
            openai.APIConnectionError,
            openai.InternalServerError,
            openai.RateLimitError,
        ),
    )


@retry(
    retry=retry_if_exception_type(
        (
            openai.APITimeoutError,
            openai.APIConnectionError,
            openai.InternalServerError,
            openai.RateLimitError,
        )
    ),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=16),
    reraise=True,
)
async def _call_responses_api(
    client: AsyncOpenAI,
    *,
    input_items: list[dict[str, Any]],
    previous_response_id: str | None,
    settings: Any,
) -> Any:
    kwargs: dict[str, Any] = {
        "model": settings.openai_model,
        "instructions": SYSTEM_PROMPT,
        "tools": TOOLS_SCHEMAS,
        "input": input_items,
        "temperature": settings.openai_temperature,
        "max_output_tokens": settings.openai_max_tokens,
    }
    if previous_response_id:
        kwargs["previous_response_id"] = previous_response_id

    return await client.responses.create(**kwargs)


# ── Public agent entry point ──────────────────────────────────────────────────

async def run_agent(
    session_id: str,
    user_message: str,
    user_id: str | None = None,
) -> dict[str, Any]:
    """
    Process one user turn and return a result dict:
      {
        "session_id":           str,
        "response_id":          str,   # to be passed as previous_response_id next turn
        "reply":                str,   # assistant text
        "tools_called":         list,  # names of tools invoked
        "input_tokens":         int,
        "output_tokens":        int,
      }
    """
    settings = get_settings()
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    with tracer.start_as_current_span("agent.run") as span:
        span.set_attribute("session_id", session_id)
        span.set_attribute("user_id", user_id or "anonymous")

        # ── Load session state ─────────────────────────────────────────────
        session = await short_term.get_session(session_id)
        # session = list of {"role": ..., "content": ..., "response_id": ...}

        previous_response_id: str | None = None
        if session:
            # The last assistant message may carry a response_id for continuity
            for msg in reversed(session):
                if msg.get("role") == "assistant" and msg.get("response_id"):
                    previous_response_id = msg["response_id"]
                    break

        # ── Build input ────────────────────────────────────────────────────
        # For the Responses API the "input" is just the new user message
        # (history continuity is handled by previous_response_id).
        input_items: list[dict[str, Any]] = [
            {"role": "user", "content": user_message}
        ]

        tools_called: list[str] = []
        response_id: str = ""
        reply: str = ""
        input_tokens: int = 0
        output_tokens: int = 0

        # ── Agentic tool loop ──────────────────────────────────────────────
        for round_n in range(_MAX_TOOL_ROUNDS):
            span.set_attribute("tool_round", round_n)
            logger.debug(
                "Agent loop round %d | session=%s | prev_id=%s",
                round_n, session_id, previous_response_id,
            )

            try:
                response = await _call_responses_api(
                    client,
                    input_items=input_items,
                    previous_response_id=previous_response_id,
                    settings=settings,
                )
            except openai.OpenAIError as exc:
                logger.error("OpenAI API error: %s", exc)
                raise

            response_id = response.id
            input_tokens += getattr(response.usage, "input_tokens", 0)
            output_tokens += getattr(response.usage, "output_tokens", 0)

            # Collect text outputs and tool calls from the response
            text_parts: list[str] = []
            tool_call_items: list[dict[str, Any]] = []

            for item in response.output:
                if item.type == "message":
                    for content_block in item.content:
                        if content_block.type == "output_text":
                            text_parts.append(content_block.text)
                elif item.type == "function_call":
                    tool_call_items.append(item)

            if text_parts:
                reply = "\n".join(text_parts)

            # ── No more tool calls — we're done ───────────────────────────
            if not tool_call_items:
                break

            # ── Execute tool calls ────────────────────────────────────────
            # The next API call sends the tool results as function_call_output
            # items.  We set previous_response_id so the model has context.
            previous_response_id = response_id
            input_items = []

            for tc in tool_call_items:
                tool_name: str = tc.name
                tool_args: str = tc.arguments
                call_id: str = tc.call_id

                logger.info("Calling tool '%s' args=%s", tool_name, tool_args[:200])
                span.set_attribute(f"tool.{round_n}.{tool_name}", tool_args[:200])
                tools_called.append(tool_name)

                result_json = await dispatch(tool_name, tool_args)
                input_items.append(
                    {
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": result_json if result_json else "{}",
                    }
                )
        else:
            logger.warning("Reached max tool rounds (%d) for session %s", _MAX_TOOL_ROUNDS, session_id)

        # ── Persist to short-term memory ───────────────────────────────────
        session.append({"role": "user", "content": user_message})
        session.append(
            {
                "role": "assistant",
                "content": reply,
                "response_id": response_id,
                "tools_called": tools_called,
            }
        )
        await short_term.save_session(session_id, session)

        span.set_attribute("tools_called", str(tools_called))
        span.set_attribute("output_tokens", output_tokens)

        return {
            "session_id": session_id,
            "response_id": response_id,
            "reply": reply,
            "tools_called": tools_called,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }
