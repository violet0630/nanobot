"""Dashboard web UI channel — serves a local web app with WebSocket communication."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from loguru import logger

from nanobot.bus.events import OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.channels.base import BaseChannel
from nanobot.config.schema import DashboardConfig


class DashboardChannel(BaseChannel):
    """
    Local web dashboard channel.

    Serves static files and communicates with the frontend via WebSocket.
    Integrates with the MessageBus exactly like Feishu/Telegram channels.
    """

    name: str = "dashboard"

    def __init__(self, config: DashboardConfig, bus: MessageBus, agent_registry=None):
        super().__init__(config, bus)
        self.host = config.host
        self.port = config.port
        self.agent_registry = agent_registry
        self._ws_connections: dict[str, Any] = {}  # session_id -> websocket
        self._server = None
        self._outbound_task: asyncio.Task | None = None

    def is_allowed(self, sender_id: str) -> bool:
        """Dashboard is local-only, always allow."""
        return True

    async def start(self) -> None:
        """Start the FastAPI server with WebSocket support."""
        import uvicorn
        from fastapi import FastAPI, WebSocket, WebSocketDisconnect
        from fastapi.staticfiles import StaticFiles
        from fastapi.responses import FileResponse

        app = FastAPI(title="Nanobot Dashboard")
        static_dir = Path(__file__).parent / "dashboard" / "static"

        @app.get("/")
        async def index():
            return FileResponse(static_dir / "index.html")

        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

        @app.get("/api/nodes")
        async def get_nodes():
            """Return registered agent nodes."""
            if not self.agent_registry:
                return {"nodes": []}
            agents = self.agent_registry.list_all_agents()
            nodes = []
            for a in agents:
                nodes.append({
                    "did": a.get("did", ""),
                    "name": a.get("name", ""),
                    "description": a.get("description", ""),
                    "ad_url": a.get("ad_url", ""),
                    "capabilities": a.get("capabilities", []),
                })
            return {"nodes": nodes}

        @app.websocket("/ws")
        async def websocket_endpoint(ws: WebSocket):
            await ws.accept()
            session_id = f"ws_{id(ws)}_{int(time.time())}"
            self._ws_connections[session_id] = ws
            logger.info("Dashboard WebSocket connected: {}", session_id)

            try:
                # Send initial nodes list
                await self._send_nodes(ws)

                while True:
                    raw = await ws.receive_text()
                    try:
                        data = json.loads(raw)
                    except json.JSONDecodeError:
                        await ws.send_text(json.dumps({"type": "error", "content": "Invalid JSON"}))
                        continue

                    msg_type = data.get("type", "")
                    content = data.get("content", "").strip()

                    if not content and msg_type in ("chat", "node_chat"):
                        continue

                    if msg_type == "chat":
                        # Home view: direct chat with local agent
                        await self._handle_message(
                            sender_id="dashboard_user",
                            chat_id=f"home_{session_id}",
                            content=content,
                            metadata={"ws_session": session_id, "dashboard_type": "home"},
                        )

                    elif msg_type == "node_chat":
                        # Node view: message targeting a specific node
                        target_node = data.get("target_node", "")
                        if not target_node:
                            await ws.send_text(json.dumps({"type": "error", "content": "Missing target_node"}))
                            continue
                        # Prefix content with routing instruction for the LLM
                        routed_content = content
                        await self._handle_message(
                            sender_id="dashboard_user",
                            chat_id=f"node_{target_node}_{session_id}",
                            content=routed_content,
                            metadata={
                                "ws_session": session_id,
                                "dashboard_type": "node",
                                "target_node": target_node,
                            },
                        )

                    elif msg_type == "get_nodes":
                        await self._send_nodes(ws)

            except WebSocketDisconnect:
                logger.info("Dashboard WebSocket disconnected: {}", session_id)
            except Exception as e:
                logger.error("Dashboard WebSocket error: {}", e)
            finally:
                self._ws_connections.pop(session_id, None)

        self._running = True

        # Start outbound message dispatcher
        self._outbound_task = asyncio.create_task(self._dispatch_to_ws())

        config = uvicorn.Config(
            app,
            host=self.host,
            port=self.port,
            log_level="warning",
            access_log=False,
        )
        self._server = uvicorn.Server(config)
        logger.info("Dashboard started at http://{}:{}", self.host, self.port)
        await self._server.serve()

    async def stop(self) -> None:
        """Stop the dashboard server."""
        self._running = False
        if self._outbound_task:
            self._outbound_task.cancel()
            try:
                await self._outbound_task
            except asyncio.CancelledError:
                pass
        if self._server:
            self._server.should_exit = True
        # Close all WebSocket connections
        for ws in list(self._ws_connections.values()):
            try:
                await ws.close()
            except Exception:
                pass
        self._ws_connections.clear()

    async def send(self, msg: OutboundMessage) -> None:
        """Send an outbound message to the appropriate WebSocket client."""
        # Extract ws_session from chat_id (format: "home_{session_id}" or "node_{did}_{session_id}")
        chat_id = msg.chat_id
        ws_session = None
        metadata = msg.metadata or {}

        # Try to find session from chat_id
        parts = chat_id.split("_")
        if len(parts) >= 2:
            if parts[0] == "home":
                ws_session = "_".join(parts[1:])
            elif parts[0] == "node" and len(parts) >= 3:
                # node_{did_parts}_{ws_xxx_timestamp}
                # Find the ws_ prefix in parts
                for i, p in enumerate(parts[1:], 1):
                    if p == "ws":
                        ws_session = "_".join(parts[i:])
                        break

        if not ws_session:
            ws_session = metadata.get("ws_session")

        if not ws_session or ws_session not in self._ws_connections:
            # Broadcast to all connections as fallback
            for sid, ws in list(self._ws_connections.items()):
                try:
                    await self._send_message_to_ws(ws, msg, chat_id)
                except Exception:
                    self._ws_connections.pop(sid, None)
            return

        ws = self._ws_connections.get(ws_session)
        if ws:
            try:
                await self._send_message_to_ws(ws, msg, chat_id)
            except Exception:
                self._ws_connections.pop(ws_session, None)

    async def _send_message_to_ws(self, ws: Any, msg: OutboundMessage, chat_id: str) -> None:
        """Format and send a message to a WebSocket client."""
        is_progress = (msg.metadata or {}).get("_progress", False)
        is_tool_hint = (msg.metadata or {}).get("_tool_hint", False)

        # Determine message context
        dashboard_type = "home"
        target_node = ""
        if chat_id.startswith("node_"):
            dashboard_type = "node"
            # Extract node DID from chat_id
            parts = chat_id.split("_")
            # Reconstruct DID (everything between "node_" and "_ws_")
            did_parts = []
            for p in parts[1:]:
                if p == "ws":
                    break
                did_parts.append(p)
            target_node = "_".join(did_parts) if did_parts else ""

        payload = {
            "type": "progress" if is_progress else "message",
            "content": msg.content or "",
            "sender": "agent",
            "dashboard_type": dashboard_type,
            "target_node": target_node,
            "is_tool_hint": is_tool_hint,
            "timestamp": time.time(),
        }
        await ws.send_text(json.dumps(payload, ensure_ascii=False))

    async def _send_nodes(self, ws: Any) -> None:
        """Send the current nodes list to a WebSocket client."""
        nodes = []
        if self.agent_registry:
            agents = self.agent_registry.list_all_agents()
            for a in agents:
                nodes.append({
                    "did": a.get("did", ""),
                    "name": a.get("name", ""),
                    "description": a.get("description", ""),
                    "ad_url": a.get("ad_url", ""),
                    "capabilities": a.get("capabilities", []),
                })
        await ws.send_text(json.dumps({
            "type": "nodes",
            "nodes": nodes,
            "timestamp": time.time(),
        }, ensure_ascii=False))

    async def _dispatch_to_ws(self) -> None:
        """
        Secondary outbound dispatcher for dashboard.

        The main ChannelManager._dispatch_outbound() handles routing OutboundMessages
        to channel.send(). This task is NOT needed because ChannelManager already does it.
        But we keep it as a no-op placeholder in case we need dashboard-specific dispatching later.
        """
        # This is intentionally empty — ChannelManager handles outbound dispatch.
        # We just keep the task alive so the channel stays running.
        try:
            while self._running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
