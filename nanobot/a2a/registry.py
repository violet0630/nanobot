"""Agent Card registry for A2A servers.

This module provides a registry for discovering, caching, and querying
Agent Cards from configured A2A servers.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from nanobot.config.schema import A2AServerConfig


class AgentCardRegistry:
    """Registry for A2A Agent Cards.

    Manages the discovery and caching of Agent Cards from multiple
    A2A servers, with automatic refresh capabilities.
    """

    def __init__(
        self,
        servers: dict[str, A2AServerConfig],
        refresh_interval: int = 300,
    ):
        """Initialize the Agent Card registry.

        Args:
            servers: Dictionary mapping server names to their configurations.
            refresh_interval: Seconds between automatic card refreshes (0 to disable).
        """
        self.servers = servers
        self.refresh_interval = refresh_interval
        self._cards: dict[str, dict[str, Any]] = {}
        self._refresh_task: asyncio.Task | None = None
        self._running = False

    async def refresh_cards(self) -> None:
        """Fetch latest Agent Cards from all configured servers."""
        if not self.servers:
            logger.debug("No A2A servers configured, skipping card refresh")
            return

        logger.info("Refreshing Agent Cards from {} servers", len(self.servers))

        for name, config in self.servers.items():
            if not config.enabled:
                continue

            try:
                await self._fetch_card(name, config)
            except Exception as e:
                logger.warning("Failed to fetch Agent Card from '{}': {}", name, e)

    async def _fetch_card(self, name: str, config: A2AServerConfig) -> None:
        """Fetch Agent Card from a single server.

        Args:
            name: Server identifier.
            config: Server configuration.
        """
        try:
            import httpx

            from a2a.client.card_resolver import A2ACardResolver
            from a2a.types import AgentCard

            async with httpx.AsyncClient(timeout=30.0) as client:
                resolver = A2ACardResolver(client, config.url)
                card = await resolver.get_agent_card()

                # Extract relevant information for LLM context
                self._cards[name] = {
                    "name": card.name,
                    "description": card.description,
                    "url": config.url,
                    "skills": [
                        {
                            "id": skill.id,
                            "name": skill.name,
                            "description": skill.description,
                            "tags": skill.tags,
                            "examples": skill.examples or [],
                        }
                        for skill in card.skills
                    ],
                    "capabilities": {
                        "streaming": card.capabilities.streaming if card.capabilities else False,
                        "push_notifications": (
                            card.capabilities.push_notifications
                            if card.capabilities
                            else False
                        ),
                    },
                    "card": card,  # Store full card for internal use
                }

                logger.info(
                    "Fetched Agent Card for '{}' with {} skills",
                    name,
                    len(card.skills),
                )
        except ImportError:
            logger.warning("a2a-sdk not installed, cannot fetch Agent Cards")
        except Exception as e:
            logger.error("Error fetching Agent Card from '{}': {}", name, e)
            raise

    def find_agents_by_skill(self, skill_tag: str) -> list[dict[str, Any]]:
        """Find agents that have a specific skill tag.

        Args:
            skill_tag: Skill tag to search for (case-insensitive partial match).

        Returns:
            List of agent info dictionaries matching the skill.
        """
        results = []
        skill_tag_lower = skill_tag.lower()

        for name, card_info in self._cards.items():
            for skill in card_info.get("skills", []):
                if skill_tag_lower in skill.get("name", "").lower():
                    results.append({"server": name, **card_info})
                    break
                for tag in skill.get("tags", []):
                    if skill_tag_lower in tag.lower():
                        results.append({"server": name, **card_info})
                        break

        return results

    def find_agents_by_tag(self, tag: str) -> list[dict[str, Any]]:
        """Find agents that have a specific tag in their skills.

        Args:
            tag: Tag to search for (case-insensitive partial match).

        Returns:
            List of agent info dictionaries matching the tag.
        """
        results = []
        tag_lower = tag.lower()

        for name, card_info in self._cards.items():
            for skill in card_info.get("skills", []):
                for skill_tag in skill.get("tags", []):
                    if tag_lower in skill_tag.lower():
                        results.append({"server": name, **card_info})
                        break

        return results

    def get_all_cards(self) -> dict[str, dict[str, Any]]:
        """Get all cached Agent Cards.

        Returns:
            Dictionary mapping server names to their card info.
        """
        return self._cards.copy()

    def get_card(self, server_name: str) -> dict[str, Any] | None:
        """Get a specific Agent Card by server name.

        Args:
            server_name: Name of the configured server.

        Returns:
            Agent card info, or None if not found.
        """
        return self._cards.get(server_name)

    def format_for_llm(self) -> str:
        """Format available agents and their skills for LLM context.

        Returns:
            Formatted string describing available A2A agents.
        """
        if not self._cards:
            return ""

        lines = ["Available A2A agents (remote agents you can delegate to):"]

        for name, card_info in self._cards.items():
            agent_name = card_info.get("name", name)
            description = card_info.get("description", "")
            url = card_info.get("url", "")

            lines.append(f"\n- {name} ({agent_name})")
            lines.append(f"  URL: {url}")
            if description:
                lines.append(f"  Description: {description}")

            skills = card_info.get("skills", [])
            if skills:
                lines.append("  Skills:")
                for skill in skills:
                    skill_name = skill.get("name", skill.get("id", "unknown"))
                    skill_desc = skill.get("description", "")
                    tags = skill.get("tags", [])
                    tag_str = f" [{', '.join(tags)}]" if tags else ""
                    lines.append(f"    - {skill_name}{tag_str}: {skill_desc}")

        return "\n".join(lines)

    def get_server_names(self) -> list[str]:
        """Get list of configured and connected server names.

        Returns:
            List of server names.
        """
        return list(self._cards.keys())

    async def start_auto_refresh(self) -> None:
        """Start automatic card refresh in the background."""
        if self._running or self.refresh_interval <= 0:
            return

        self._running = True

        async def _refresh_loop():
            while self._running:
                try:
                    await asyncio.sleep(self.refresh_interval)
                    if self._running:
                        await self.refresh_cards()
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.warning("Error in card refresh loop: {}", e)

        self._refresh_task = asyncio.create_task(_refresh_loop())

    async def stop_auto_refresh(self) -> None:
        """Stop automatic card refresh."""
        self._running = False
        if self._refresh_task:
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass
            self._refresh_task = None
