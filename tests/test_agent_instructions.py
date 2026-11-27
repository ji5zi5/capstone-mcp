# Copyright 2026 Capstone MCP contributors.
"""Guidance must survive clients that truncate initialization instructions."""

import asyncio
import re

from mcp.types import TextContent

from capstone_mcp.agent_instructions import (
    CLIENT_INSTRUCTION_LIMIT,
    GUIDE,
    INSTRUCTIONS,
    guide,
)
from capstone_mcp.server import MCP


def test_initial_instructions_fit_the_observed_client_limit() -> None:
    # Given: a client that keeps only the first 4096 characters.
    # Then: nothing essential can be cut off.
    assert len(INSTRUCTIONS) <= CLIENT_INSTRUCTION_LIMIT


def test_every_guide_topic_is_announced_in_the_initial_instructions() -> None:
    for topic in GUIDE:
        assert topic in INSTRUCTIONS
    assert "capstone://guide" in INSTRUCTIONS


def test_guidance_names_only_discoverable_mcp_tools() -> None:
    tools = {tool.name for tool in asyncio.run(MCP.list_tools())}
    references = set(re.findall(r"\bcapstone_[a-z_]+", INSTRUCTIONS + guide()))
    assert references
    assert references <= tools, references - tools


def test_single_topic_returns_only_that_section() -> None:
    # When
    text = guide("recovery")
    # Then
    assert text.startswith("FAILURE AND RECOVERY")
    assert "SAVE AND EXPORT" not in text


def test_guide_without_a_topic_returns_every_section_in_order() -> None:
    # When
    text = guide()
    # Then
    positions = [text.index(section.strip()) for section in GUIDE.values()]
    assert positions == sorted(positions)


def test_guided_prompts_name_only_discoverable_mcp_tools() -> None:
    async def read_prompts() -> tuple[set[str], str]:
        tools = {tool.name for tool in await MCP.list_tools()}
        rendered: list[str] = []
        for prompt in await MCP.list_prompts():
            result = await MCP.get_prompt(prompt.name, {})
            rendered.extend(
                message.content.text for message in result.messages
                if isinstance(message.content, TextContent)
            )
        return tools, "\n".join(rendered)

    tools, text = asyncio.run(read_prompts())
    references = set(re.findall(r"\bcapstone_[a-z_]+", text))
    assert references
    assert references <= tools, references - tools
