# Copyright 2026 Capstone MCP contributors.
"""Guidance must survive clients that truncate initialization instructions."""

from capstone_mcp.agent_instructions import (
    CLIENT_INSTRUCTION_LIMIT,
    GUIDE,
    INSTRUCTIONS,
    guide,
)


def test_initial_instructions_fit_the_observed_client_limit() -> None:
    # Given: a client that keeps only the first 4096 characters.
    # Then: nothing essential can be cut off.
    assert len(INSTRUCTIONS) <= CLIENT_INSTRUCTION_LIMIT


def test_every_guide_topic_is_announced_in_the_initial_instructions() -> None:
    for topic in GUIDE:
        assert topic in INSTRUCTIONS
    assert "capstone_guide(topic)" in INSTRUCTIONS


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
