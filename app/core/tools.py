import json
from contextlib import AsyncExitStack
from pathlib import Path

import structlog
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.config import settings

logger = structlog.get_logger()


class MCPServerConnection:
    """A single MCP server connection."""

    def __init__(self, name: str, session: ClientSession, tools: list):
        self.name = name
        self.session = session
        self.tools = tools  # list of mcp Tool objects


class ToolManager:
    """Manages MCP server connections and tool execution."""

    def __init__(self):
        self._exit_stack: AsyncExitStack | None = None
        self._servers: dict[str, MCPServerConnection] = {}
        self._tool_map: dict[str, MCPServerConnection] = {}  # tool_name -> server

    async def initialize(self):
        """Start all MCP servers from config file."""
        config_path = Path(settings.MCP_SERVERS_CONFIG)
        if not config_path.exists():
            logger.info("tools.no_config", path=str(config_path))
            return

        try:
            config = json.loads(config_path.read_text())
        except Exception:
            logger.exception("tools.config_parse_failed", path=str(config_path))
            return

        servers = config.get("servers", [])
        if not servers:
            logger.info("tools.no_servers_configured")
            return

        self._exit_stack = AsyncExitStack()

        for server_config in servers:
            name = server_config.get("name", "unknown")
            try:
                await self._connect_server(name, server_config)
            except Exception:
                logger.exception("tools.server_connect_failed", server=name)

        tool_count = len(self._tool_map)
        logger.info("tools.initialized", servers=len(self._servers), tools=tool_count)

    async def _connect_server(self, name: str, config: dict):
        """Connect to a single MCP server via stdio."""
        params = StdioServerParameters(
            command=config["command"],
            args=config.get("args", []),
            env=config.get("env"),
        )

        read_stream, write_stream = await self._exit_stack.enter_async_context(
            stdio_client(params)
        )
        session = await self._exit_stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        await session.initialize()

        # List available tools
        tools_result = await session.list_tools()
        tools = tools_result.tools

        conn = MCPServerConnection(name=name, session=session, tools=tools)
        self._servers[name] = conn

        for tool in tools:
            if tool.name in self._tool_map:
                existing = self._tool_map[tool.name].name
                logger.warning(
                    "tools.name_collision",
                    tool=tool.name,
                    existing_server=existing,
                    new_server=name,
                )
            self._tool_map[tool.name] = conn
            logger.info("tools.registered", server=name, tool=tool.name)

    def get_tools_schema(self) -> list[dict]:
        """Return all tools in OpenAI function calling format."""
        tools = []
        for tool_name, conn in self._tool_map.items():
            for tool in conn.tools:
                if tool.name == tool_name:
                    tools.append({
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description": tool.description or "",
                            "parameters": tool.inputSchema,
                        },
                    })
        return tools

    async def execute_tool(self, name: str, arguments: dict) -> str:
        """Execute a tool by name and return text result."""
        conn = self._tool_map.get(name)
        if not conn:
            return f"Error: Unknown tool '{name}'"

        try:
            result = await conn.session.call_tool(name, arguments)
            # Extract text content from result blocks
            text_parts = []
            for block in result.content:
                if hasattr(block, "text"):
                    text_parts.append(block.text)
            return "\n".join(text_parts) if text_parts else "Tool returned no text output."
        except Exception:
            logger.exception("tools.execute_failed", tool=name)
            return f"Error executing tool '{name}'"

    @property
    def has_tools(self) -> bool:
        return len(self._tool_map) > 0

    async def shutdown(self):
        """Close all MCP server connections."""
        if self._exit_stack:
            await self._exit_stack.aclose()
            self._servers.clear()
            self._tool_map.clear()
            logger.info("tools.shutdown")


tool_manager = ToolManager()
