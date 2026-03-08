"""Agent loop: the core processing engine."""

from __future__ import annotations

import asyncio
import json
import re
import weakref
from contextlib import AsyncExitStack
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from loguru import logger

from nanobot.agent.context import ContextBuilder
from nanobot.agent.memory import MemoryStore
from nanobot.agent.subagent import SubagentManager
from nanobot.agent.tools.cron import CronTool
from nanobot.agent.tools.filesystem import EditFileTool, ListDirTool, ReadFileTool, WriteFileTool
from nanobot.agent.tools.message import MessageTool
from nanobot.agent.tools.registry import ToolRegistry
from nanobot.agent.tools.shell import ExecTool
from nanobot.agent.tools.spawn import SpawnTool
from nanobot.agent.tools.web import WebFetchTool, WebSearchTool
from nanobot.bus.events import InboundMessage, OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.providers.base import LLMProvider
from nanobot.session.manager import Session, SessionManager

if TYPE_CHECKING:
    from nanobot.config.schema import ChannelsConfig, ExecToolConfig
    from nanobot.cron.service import CronService


class AgentLoop:
    """
    The agent loop is the core processing engine.

    It:
    1. Receives messages from the bus
    2. Builds context with history, memory, skills
    3. Calls the LLM
    4. Executes tool calls
    5. Sends responses back
    """

    _TOOL_RESULT_MAX_CHARS = 500

    def __init__(
        self,
        bus: MessageBus,
        provider: LLMProvider,
        workspace: Path,
        model: str | None = None,
        max_iterations: int = 40,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        memory_window: int = 100,
        reasoning_effort: str | None = None,
        brave_api_key: str | None = None,
        web_proxy: str | None = None,
        exec_config: ExecToolConfig | None = None,
        cron_service: CronService | None = None,
        restrict_to_workspace: bool = False,
        session_manager: SessionManager | None = None,
        mcp_servers: dict | None = None,
        channels_config: ChannelsConfig | None = None,
    ):
        from nanobot.config.schema import ExecToolConfig
        self.bus = bus
        self.channels_config = channels_config
        self.provider = provider
        self.workspace = workspace
        self.model = model or provider.get_default_model()
        self.max_iterations = max_iterations
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.memory_window = memory_window
        self.reasoning_effort = reasoning_effort
        self.brave_api_key = brave_api_key
        self.web_proxy = web_proxy
        self.exec_config = exec_config or ExecToolConfig()
        self.cron_service = cron_service
        self.restrict_to_workspace = restrict_to_workspace

        self.context = ContextBuilder(workspace)
        self.sessions = session_manager or SessionManager(workspace)
        self.tools = ToolRegistry()
        self.subagents = SubagentManager(
            provider=provider,
            workspace=workspace,
            bus=bus,
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            reasoning_effort=reasoning_effort,
            brave_api_key=brave_api_key,
            web_proxy=web_proxy,
            exec_config=self.exec_config,
            restrict_to_workspace=restrict_to_workspace,
        )

        self._running = False
        self._mcp_servers = mcp_servers or {}
        self._mcp_stack: AsyncExitStack | None = None
        self._mcp_connected = False
        self._mcp_connecting = False
        self._consolidating: set[str] = set()  # Session keys with consolidation in progress
        self._consolidation_tasks: set[asyncio.Task] = set()  # Strong refs to in-flight tasks
        self._consolidation_locks: weakref.WeakValueDictionary[str, asyncio.Lock] = weakref.WeakValueDictionary()
        self._active_tasks: dict[str, list[asyncio.Task]] = {}  # session_key -> tasks
        self._processing_lock = asyncio.Lock()
        self._anp_server = None
        self._anp_config = None  # Store ANP config for later startup
        self._last_active_user: dict[str, str] = {}  # channel -> chat_id for ANP notifications
        self._register_default_tools()
        self._register_anp_tools()

    def _register_default_tools(self) -> None:
        """Register the default set of tools."""
        allowed_dir = self.workspace if self.restrict_to_workspace else None
        for cls in (ReadFileTool, WriteFileTool, EditFileTool, ListDirTool):
            self.tools.register(cls(workspace=self.workspace, allowed_dir=allowed_dir))
        self.tools.register(ExecTool(
            working_dir=str(self.workspace),
            timeout=self.exec_config.timeout,
            restrict_to_workspace=self.restrict_to_workspace,
            path_append=self.exec_config.path_append,
        ))
        self.tools.register(WebSearchTool(api_key=self.brave_api_key, proxy=self.web_proxy))
        self.tools.register(WebFetchTool(proxy=self.web_proxy))
        self.tools.register(MessageTool(send_callback=self.bus.publish_outbound))
        self.tools.register(SpawnTool(manager=self.subagents))
        if self.cron_service:
            self.tools.register(CronTool(self.cron_service))

    def _register_anp_tools(self) -> None:
        """Register ANP (Agent Network Protocol) tools if enabled."""
        try:
            from nanobot.skills.anp.tool import (
                ANPCallTool,
                ANPListAgentsTool,
                ANPGetAgentInfoTool,
            )
            from nanobot.config.loader import load_config

            # Load ANP config from config file
            config = load_config()
            anp_config = getattr(config, 'anp', None) or getattr(config.channels, 'anp', None)

            # Check if ANP is enabled in config
            if anp_config and getattr(anp_config, "enabled", False):
                self.tools.register(ANPCallTool())
                self.tools.register(ANPListAgentsTool())
                self.tools.register(ANPGetAgentInfoTool())
                logger.info("ANP tools registered")

                # Store config for later async startup
                self._anp_config = anp_config
        except ImportError as e:
            logger.debug("ANP tools not available: {}", e)
        except Exception as e:
            logger.warning("Failed to register ANP tools: {}", e)

    async def _start_anp_server_async(self) -> None:
        """Start the ANP server for receiving external requests (async version)."""
        if not self._anp_config:
            return

        try:
            from nanobot.anp.server import ANPServer

            self._anp_server = ANPServer(
                bus=self.bus,
                host=getattr(self._anp_config, "host", "0.0.0.0"),
                port=getattr(self._anp_config, "port", 8080),
                jwt_secret=getattr(self._anp_config, "jwt_secret", "your-secret-key"),
                auth_enabled=getattr(self._anp_config, "auth_enabled", True),
                agent_registry_path=getattr(self._anp_config, "agent_registry_path", None),
                agent_loop=self,  # Pass agent loop reference
            )

            # Start server in background
            await self._anp_server.start()
            logger.info("ANP server started on port {}", getattr(self._anp_config, "port", 8080))
        except ImportError:
            logger.warning("FastAPI not available, ANP server not started")
        except Exception as e:
            logger.error("Failed to start ANP server: {}", e)

    async def _connect_mcp(self) -> None:
        """Connect to configured MCP servers (one-time, lazy)."""
        if self._mcp_connected or self._mcp_connecting or not self._mcp_servers:
            return
        self._mcp_connecting = True
        from nanobot.agent.tools.mcp import connect_mcp_servers
        try:
            self._mcp_stack = AsyncExitStack()
            await self._mcp_stack.__aenter__()
            await connect_mcp_servers(self._mcp_servers, self.tools, self._mcp_stack)
            self._mcp_connected = True
        except Exception as e:
            logger.error("Failed to connect MCP servers (will retry next message): {}", e)
            if self._mcp_stack:
                try:
                    await self._mcp_stack.aclose()
                except Exception:
                    pass
                self._mcp_stack = None
        finally:
            self._mcp_connecting = False

    def _set_tool_context(self, channel: str, chat_id: str, message_id: str | None = None) -> None:
        """Update context for all tools that need routing info."""
        for name in ("message", "spawn", "cron"):
            if tool := self.tools.get(name):
                if hasattr(tool, "set_context"):
                    tool.set_context(channel, chat_id, *([message_id] if name == "message" else []))

    @staticmethod
    def _strip_think(text: str | None) -> str | None:
        """Remove <think>…</think> blocks that some models embed in content."""
        if not text:
            return None
        return re.sub(r"<think>[\s\S]*?</think>", "", text).strip() or None

    @staticmethod
    def _tool_hint(tool_calls: list) -> str:
        """Format tool calls as concise hint, e.g. 'web_search("query")'."""
        def _fmt(tc):
            args = (tc.arguments[0] if isinstance(tc.arguments, list) else tc.arguments) or {}
            val = next(iter(args.values()), None) if isinstance(args, dict) else None
            if not isinstance(val, str):
                return tc.name
            return f'{tc.name}("{val[:40]}…")' if len(val) > 40 else f'{tc.name}("{val}")'
        return ", ".join(_fmt(tc) for tc in tool_calls)

    async def _run_agent_loop(
        self,
        initial_messages: list[dict],
        on_progress: Callable[..., Awaitable[None]] | None = None,
    ) -> tuple[str | None, list[str], list[dict]]:
        """Run the agent iteration loop. Returns (final_content, tools_used, messages)."""
        messages = initial_messages
        iteration = 0
        final_content = None
        tools_used: list[str] = []

        while iteration < self.max_iterations:
            iteration += 1

            response = await self.provider.chat(
                messages=messages,
                tools=self.tools.get_definitions(),
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                reasoning_effort=self.reasoning_effort,
            )

            if response.has_tool_calls:
                if on_progress:
                    clean = self._strip_think(response.content)
                    if clean:
                        await on_progress(clean)
                    await on_progress(self._tool_hint(response.tool_calls), tool_hint=True)

                tool_call_dicts = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments, ensure_ascii=False)
                        }
                    }
                    for tc in response.tool_calls
                ]
                messages = self.context.add_assistant_message(
                    messages, response.content, tool_call_dicts,
                    reasoning_content=response.reasoning_content,
                    thinking_blocks=response.thinking_blocks,
                )

                for tool_call in response.tool_calls:
                    tools_used.append(tool_call.name)
                    args_str = json.dumps(tool_call.arguments, ensure_ascii=False)
                    logger.info("Tool call: {}({})", tool_call.name, args_str[:200])
                    result = await self.tools.execute(tool_call.name, tool_call.arguments)
                    messages = self.context.add_tool_result(
                        messages, tool_call.id, tool_call.name, result
                    )
            else:
                clean = self._strip_think(response.content)
                # Don't persist error responses to session history — they can
                # poison the context and cause permanent 400 loops (#1303).
                if response.finish_reason == "error":
                    logger.error("LLM returned error: {}", (clean or "")[:200])
                    final_content = clean or "Sorry, I encountered an error calling the AI model."
                    break
                messages = self.context.add_assistant_message(
                    messages, clean, reasoning_content=response.reasoning_content,
                    thinking_blocks=response.thinking_blocks,
                )
                final_content = clean
                break

        if final_content is None and iteration >= self.max_iterations:
            logger.warning("Max iterations ({}) reached", self.max_iterations)
            final_content = (
                f"I reached the maximum number of tool call iterations ({self.max_iterations}) "
                "without completing the task. You can try breaking the task into smaller steps."
            )

        return final_content, tools_used, messages

    async def run(self) -> None:
        """Run the agent loop, dispatching messages as tasks to stay responsive to /stop."""
        self._running = True
        await self._connect_mcp()
        await self._start_anp_server_async()
        logger.info("Agent loop started")

        while self._running:
            try:
                msg = await asyncio.wait_for(self.bus.consume_inbound(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            if msg.content.strip().lower() == "/stop":
                await self._handle_stop(msg)
            else:
                task = asyncio.create_task(self._dispatch(msg))
                self._active_tasks.setdefault(msg.session_key, []).append(task)
                task.add_done_callback(lambda t, k=msg.session_key: self._active_tasks.get(k, []) and self._active_tasks[k].remove(t) if t in self._active_tasks.get(k, []) else None)

    async def _handle_stop(self, msg: InboundMessage) -> None:
        """Cancel all active tasks and subagents for the session."""
        tasks = self._active_tasks.pop(msg.session_key, [])
        cancelled = sum(1 for t in tasks if not t.done() and t.cancel())
        for t in tasks:
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass
        sub_cancelled = await self.subagents.cancel_by_session(msg.session_key)
        total = cancelled + sub_cancelled
        content = f"⏹ Stopped {total} task(s)." if total else "No active task to stop."
        await self.bus.publish_outbound(OutboundMessage(
            channel=msg.channel, chat_id=msg.chat_id, content=content,
        ))

    async def _dispatch(self, msg: InboundMessage) -> None:
        """Process a message under the global lock."""
        async with self._processing_lock:
            try:
                response = await self._process_message(msg)
                if response is not None:
                    # ANP server mode: handle response correlation directly
                    if response.channel == "anp":
                        await self._complete_anp_response(response)
                    else:
                        await self.bus.publish_outbound(response)
                elif msg.channel == "cli":
                    await self.bus.publish_outbound(OutboundMessage(
                        channel=msg.channel, chat_id=msg.chat_id,
                        content="", metadata=msg.metadata or {},
                    ))
            except asyncio.CancelledError:
                logger.info("Task cancelled for session {}", msg.session_key)
                raise
            except Exception:
                logger.exception("Error processing message for session {}", msg.session_key)
                await self.bus.publish_outbound(OutboundMessage(
                    channel=msg.channel, chat_id=msg.chat_id,
                    content="Sorry, I encountered an error.",
                ))

    async def _complete_anp_response(self, response: OutboundMessage) -> None:
        """
        Complete an ANP request by setting the response_future.

        This is called when an ANP server request has been processed and the response
        needs to be sent back to the waiting HTTP request in server.py.

        Args:
            response: The OutboundMessage containing the ANP response
        """
        correlation_id = response.metadata.get("correlation_id")
        if not correlation_id:
            logger.warning("ANP response missing correlation_id")
            return

        try:
            # Import here to avoid circular dependency
            from nanobot.anp.server import complete_pending_request

            # Build the result dict
            result = {
                "status": "success",
                "content": response.content,
                "metadata": response.metadata,
            }

            # Complete the pending request future
            if complete_pending_request(correlation_id, result):
                logger.debug("ANP request completed: correlation_id={}", correlation_id)
            else:
                logger.warning("ANP request not found or already completed: correlation_id={}", correlation_id)
        except Exception as e:
            logger.error("Error completing ANP response: {}", e)

    async def close_mcp(self) -> None:
        """Close MCP connections."""
        if self._mcp_stack:
            try:
                await self._mcp_stack.aclose()
            except (RuntimeError, BaseExceptionGroup):
                pass  # MCP SDK cancel scope cleanup is noisy but harmless
            self._mcp_stack = None

    def stop(self) -> None:
        """Stop the agent loop."""
        self._running = False
        logger.info("Agent loop stopping")

    async def _process_message(
        self,
        msg: InboundMessage,
        session_key: str | None = None,
        on_progress: Callable[[str], Awaitable[None]] | None = None,
    ) -> OutboundMessage | None:
        """Process a single inbound message and return the response."""
        # System messages: parse origin from chat_id ("channel:chat_id")
        if msg.channel == "system":
            channel, chat_id = (msg.chat_id.split(":", 1) if ":" in msg.chat_id
                                else ("cli", msg.chat_id))
            logger.info("Processing system message from {}", msg.sender_id)
            key = f"{channel}:{chat_id}"
            session = self.sessions.get_or_create(key)
            self._set_tool_context(channel, chat_id, msg.metadata.get("message_id"))
            history = session.get_history(max_messages=self.memory_window)
            messages = self.context.build_messages(
                history=history,
                current_message=msg.content, channel=channel, chat_id=chat_id,
            )
            final_content, _, all_msgs = await self._run_agent_loop(messages)
            self._save_turn(session, all_msgs, 1 + len(history))
            self.sessions.save(session)
            return OutboundMessage(channel=channel, chat_id=chat_id,
                                  content=final_content or "Background task completed.")

        # ANP server mode: handle external agent requests
        if msg.channel == "anp":
            return await self._process_anp_message(msg)

        preview = msg.content[:80] + "..." if len(msg.content) > 80 else msg.content
        logger.info("Processing message from {}:{}: {}", msg.channel, msg.sender_id, preview)

        # Track the last active user for ANP notifications
        # Only track non-system, non-ANP messages from real users
        if msg.channel not in ("system", "anp") and msg.chat_id:
            self._last_active_user[msg.channel] = msg.chat_id
            logger.debug("Updated last active user for {}: {}", msg.channel, msg.chat_id)

        key = session_key or msg.session_key
        session = self.sessions.get_or_create(key)

        # Slash commands
        cmd = msg.content.strip().lower()
        if cmd == "/new":
            lock = self._consolidation_locks.setdefault(session.key, asyncio.Lock())
            self._consolidating.add(session.key)
            try:
                async with lock:
                    snapshot = session.messages[session.last_consolidated:]
                    if snapshot:
                        temp = Session(key=session.key)
                        temp.messages = list(snapshot)
                        if not await self._consolidate_memory(temp, archive_all=True):
                            return OutboundMessage(
                                channel=msg.channel, chat_id=msg.chat_id,
                                content="Memory archival failed, session not cleared. Please try again.",
                            )
            except Exception:
                logger.exception("/new archival failed for {}", session.key)
                return OutboundMessage(
                    channel=msg.channel, chat_id=msg.chat_id,
                    content="Memory archival failed, session not cleared. Please try again.",
                )
            finally:
                self._consolidating.discard(session.key)

            session.clear()
            self.sessions.save(session)
            self.sessions.invalidate(session.key)
            return OutboundMessage(channel=msg.channel, chat_id=msg.chat_id,
                                  content="New session started.")
        if cmd == "/help":
            return OutboundMessage(channel=msg.channel, chat_id=msg.chat_id,
                                  content="🐈 nanobot commands:\n/new — Start a new conversation\n/stop — Stop the current task\n/help — Show available commands")

        unconsolidated = len(session.messages) - session.last_consolidated
        if (unconsolidated >= self.memory_window and session.key not in self._consolidating):
            self._consolidating.add(session.key)
            lock = self._consolidation_locks.setdefault(session.key, asyncio.Lock())

            async def _consolidate_and_unlock():
                try:
                    async with lock:
                        await self._consolidate_memory(session)
                finally:
                    self._consolidating.discard(session.key)
                    _task = asyncio.current_task()
                    if _task is not None:
                        self._consolidation_tasks.discard(_task)

            _task = asyncio.create_task(_consolidate_and_unlock())
            self._consolidation_tasks.add(_task)

        self._set_tool_context(msg.channel, msg.chat_id, msg.metadata.get("message_id"))
        if message_tool := self.tools.get("message"):
            if isinstance(message_tool, MessageTool):
                message_tool.start_turn()

        history = session.get_history(max_messages=self.memory_window)
        initial_messages = self.context.build_messages(
            history=history,
            current_message=msg.content,
            media=msg.media if msg.media else None,
            channel=msg.channel, chat_id=msg.chat_id,
        )

        async def _bus_progress(content: str, *, tool_hint: bool = False) -> None:
            meta = dict(msg.metadata or {})
            meta["_progress"] = True
            meta["_tool_hint"] = tool_hint
            await self.bus.publish_outbound(OutboundMessage(
                channel=msg.channel, chat_id=msg.chat_id, content=content, metadata=meta,
            ))

        final_content, _, all_msgs = await self._run_agent_loop(
            initial_messages, on_progress=on_progress or _bus_progress,
        )

        if final_content is None:
            final_content = "I've completed processing but have no response to give."

        self._save_turn(session, all_msgs, 1 + len(history))
        self.sessions.save(session)

        if (mt := self.tools.get("message")) and isinstance(mt, MessageTool) and mt._sent_in_turn:
            return None

        preview = final_content[:120] + "..." if len(final_content) > 120 else final_content
        logger.info("Response to {}:{}: {}", msg.channel, msg.sender_id, preview)
        return OutboundMessage(
            channel=msg.channel, chat_id=msg.chat_id, content=final_content,
            metadata=msg.metadata or {},
        )

    def _save_turn(self, session: Session, messages: list[dict], skip: int) -> None:
        """Save new-turn messages into session, truncating large tool results."""
        from datetime import datetime
        for m in messages[skip:]:
            entry = dict(m)
            role, content = entry.get("role"), entry.get("content")
            if role == "assistant" and not content and not entry.get("tool_calls"):
                continue  # skip empty assistant messages — they poison session context
            if role == "tool" and isinstance(content, str) and len(content) > self._TOOL_RESULT_MAX_CHARS:
                entry["content"] = content[:self._TOOL_RESULT_MAX_CHARS] + "\n... (truncated)"
            elif role == "user":
                if isinstance(content, str) and content.startswith(ContextBuilder._RUNTIME_CONTEXT_TAG):
                    continue
                if isinstance(content, list):
                    entry["content"] = [
                        {"type": "text", "text": "[image]"} if (
                            c.get("type") == "image_url"
                            and c.get("image_url", {}).get("url", "").startswith("data:image/")
                        ) else c for c in content
                    ]
            entry.setdefault("timestamp", datetime.now().isoformat())
            session.messages.append(entry)
        session.updated_at = datetime.now()

    async def _consolidate_memory(self, session, archive_all: bool = False) -> bool:
        """Delegate to MemoryStore.consolidate(). Returns True on success."""
        return await MemoryStore(self.workspace).consolidate(
            session, self.provider, self.model,
            archive_all=archive_all, memory_window=self.memory_window,
        )

    def _get_user_notification_target(self) -> tuple[str, str]:
        """
        Get the user's notification channel and chat_id for ANP requests.

        Returns:
            Tuple of (channel, chat_id). If no target is configured, returns
            the first enabled channel with its default chat_id.

        Priority:
        1. ANPConfig.user_notification_target (format: "channel:chat_id")
        2. Last active user from _last_active_user (tracked from real user messages)
        3. First enabled channel from channels_config with valid chat_id
        4. Fallback to ("cli", "direct")
        """
        from nanobot.config.loader import load_config

        logger.debug(f"[ANP Server] _last_active_user: {self._last_active_user}")

        # Priority 1: Try to load ANP config from top level or channels
        try:
            config = load_config()
            anp_config = getattr(config, 'anp', None) or getattr(config.channels, 'anp', None)

            if anp_config:
                target = getattr(anp_config, "user_notification_target", "")
                logger.debug(f"[ANP Server] ANP user_notification_target from config: {target}")
                if target and ":" in target:
                    channel, chat_id = target.split(":", 1)
                    logger.info(f"[ANP Server] Using configured notification target: {channel}:{chat_id}")
                    return channel.strip(), chat_id.strip()
        except Exception as e:
            logger.warning(f"[ANP Server] Failed to load ANP config: {e}")

        # Priority 2: Use last active user (tracked from real user messages)
        # This is the most reliable source when user has sent a message
        if self._last_active_user:
            # Prefer channels in priority order
            channel_priority = ["feishu", "telegram", "discord", "matrix"]
            for channel_name in channel_priority:
                if channel_name in self._last_active_user:
                    chat_id = self._last_active_user[channel_name]
                    # Validate chat_id is not a wildcard or placeholder
                    if chat_id and chat_id != "*" and not chat_id.startswith("${"):
                        logger.info(f"[ANP Server] Using last active user for {channel_name}: {chat_id}")
                        return channel_name, chat_id
            # Fall through to config-based detection if no valid last active user

        # Priority 3: Auto-detect from config
        if self.channels_config:
            channel_priority = ["feishu", "telegram", "discord", "matrix"]
            for channel_name in channel_priority:
                channel_config = getattr(self.channels_config, channel_name, None)
                if channel_config and getattr(channel_config, "enabled", False):
                    allow_list = getattr(channel_config, "allow_from", [])
                    # Skip wildcard allow lists - we need a real user ID
                    if allow_list and allow_list[0] != "*":
                        return channel_name, allow_list[0]
                    # For matrix, use user_id
                    if channel_name == "matrix":
                        user_id = getattr(channel_config, "user_id", "")
                        if user_id:
                            return channel_name, user_id

        # Priority 4: Fallback
        return "cli", "direct"

    async def _process_anp_message(self, msg: InboundMessage) -> OutboundMessage:
        """
        Process an ANP server mode request from an external agent.

        This handles the server-side flow when an external ANP agent calls us.
        The message should include metadata with method and params from the JSON-RPC request.

        Args:
            msg: InboundMessage with channel="anp" and metadata containing method/params

        Returns:
            OutboundMessage with the result (will be sent back as JSON-RPC response)
        """
        from nanobot.templates.memory import MEMORY_MD
        from datetime import datetime

        caller_did = msg.metadata.get("caller_did", msg.sender_id)
        method = msg.metadata.get("method", "")
        params = msg.metadata.get("params", {})
        correlation_id = msg.metadata.get("correlation_id", "")

        logger.info("Processing ANP request: caller={}, method={}", caller_did, method)

        # Get user notification target (channel, chat_id)
        user_channel, user_chat_id = self._get_user_notification_target()
        logger.info("User notification target: {}:{}", user_channel, user_chat_id)

        # Set message tool context to user's channel for forwarding
        self._set_tool_context(user_channel, user_chat_id)

        # Identify the calling agent from registry for better context
        caller_info = self._get_agent_info_by_did(caller_did)
        caller_name = caller_info.get("name", "Unknown Agent") if caller_info else "Unknown Agent"
        caller_role = caller_info.get("role", "") if caller_info else ""

        # Build ANP-specific context with server mode instructions
        # Simplified prompt focused on verification code requests
        anp_system_prompt = f"""# ANP Server Mode - User Representative Agent

You are Nanobot, the User Representative Agent. You just received an ANP request from an external agent.

## CRITICAL: Response Format
You MUST respond with valid JSON only. NO tools, NO markdown, just JSON.

Your response MUST be one of these JSON objects:

1. For verification code requests (NEED USER INPUT):
   {{"status": "pending_user_approval", "message": "Description of what user needs to provide"}}

2. For requests that require forwarding to user:
   {{"status": "forward_to_user", "message": "Message to show user"}}

3. For direct responses:
   {{"status": "success", "message": "Response message"}}

4. For errors:
   {{"status": "error", "message": "Error description"}}

## Request Analysis
- **Caller**: {caller_name} ({caller_did})
- **Role**: {caller_role}
- **Method**: {method}
- **Parameters**: {json.dumps(params, indent=2, ensure_ascii=False)}

## Decision Rules

### RULE 1: Verification Code Requests
If the message contains "verification_code_request", "verification code", "security code", or similar:
- Respond with: {{"status": "pending_user_approval", "message": "A verification code is needed. Please check your messages."}}

### RULE 2: Security/Sensitive Requests
If the request is about security upgrades, data access, log access, or credentials:
- Respond with: {{"status": "forward_to_user", "message": "Security-sensitive request from {caller_name}: {method}"}}

### RULE 3: All Other Requests
- Respond with: {{"status": "success", "message": "Request processed successfully"}}

## Example
If method is "receiveNotice" and params contain "verification_code_request":
Respond: {{"status": "pending_user_approval", "message": "Verification code required for security upgrade"}}
"""

        # Build messages for LLM processing
        # ANP server mode is stateless - don't use session history to avoid tool role errors
        # Build context with ANP server instructions
        messages = [
            {"role": "system", "content": anp_system_prompt},
            {"role": "user", "content": f"ANP Request: {method} from {caller_name} ({caller_did}) with params: {json.dumps(params, ensure_ascii=False)}"}
        ]

        # For ANP server mode, use direct LLM call with JSON response format
        # This avoids the tool call loop which is not needed for simple request/response
        response = await self.provider.chat(
            messages=messages,
            tools=None,  # No tools for ANP server mode - we want direct JSON response
            model=self.model,
            temperature=0.1,  # Lower temperature for more deterministic responses
            max_tokens=1000,
        )

        final_content = response.content

        # Parse the JSON response
        try:
            result_data = json.loads(final_content) if isinstance(final_content, str) else final_content
            status = result_data.get("status", "unknown")

            # Check if this is a request that needs user notification
            if status in ["pending_user_approval", "requesting_verification", "forward_to_user"]:
                # Extract the message content to send to user
                user_message = result_data.get("message", "ANP request requires your attention")

                # Publish to bus for user notification - simpler approach
                await self.bus.publish_outbound(OutboundMessage(
                    channel=user_channel,
                    chat_id=user_chat_id,
                    content=f"[ANP Request from {caller_name}]\n\n{user_message}\n\n[Please respond to approve or deny.]"
                ))

                logger.info(f"[ANP Server] Forwarded request to user at {user_channel}:{user_chat_id}")

        except json.JSONDecodeError:
            logger.warning(f"[ANP Server] Response was not valid JSON: {final_content}")
            result_data = {"status": "error", "message": final_content}
        else:
            logger.info(f"[ANP Server] LLM response status: {status}, action: {result_data.get('action', 'N/A')}")

        # Note: Not saving to session - ANP server mode is stateless

        # Return response as OutboundMessage (will be converted to JSON-RPC by server)
        return OutboundMessage(
            channel="anp",
            chat_id=caller_did,
            content=final_content or "Request processed",
            metadata={
                "correlation_id": correlation_id,
                "caller_did": caller_did,
                "method": method,
                "user_channel": user_channel,
                "user_chat_id": user_chat_id,
            }
        )

    def _get_agent_info_by_did(self, did: str) -> dict[str, Any] | None:
        """Get agent information from registry by DID."""
        try:
            from nanobot.anp.agent_registry import AgentRegistry
            registry = AgentRegistry()
            return registry.get_by_did(did)
        except Exception:
            return None

    async def process_direct(
        self,
        content: str,
        session_key: str = "cli:direct",
        channel: str = "cli",
        chat_id: str = "direct",
        on_progress: Callable[[str], Awaitable[None]] | None = None,
    ) -> str:
        """Process a message directly (for CLI or cron usage)."""
        await self._connect_mcp()
        msg = InboundMessage(channel=channel, sender_id="user", chat_id=chat_id, content=content)
        response = await self._process_message(msg, session_key=session_key, on_progress=on_progress)
        return response.content if response else ""
