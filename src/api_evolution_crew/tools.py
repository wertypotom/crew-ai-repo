import asyncio
from crewai.tools import tool
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

import os

# A robust wrapper that creates a temporary STDIO connection to our natively linked Node MCP Server
async def _execute_mcp_tool(tool_name: str, args: dict) -> str:
    # We must pass the Python environment variables down to the Node server
    # otherwise it won't have the SUPABASE_URL keys!
    env = os.environ.copy()
    env["DOTENVX_QUIET"] = "1"  # Silences the '◇ injected env' stdout banner that breaks JSON-RPC
    
    server_params = StdioServerParameters(
        command="api-evolution-mcp",
        args=[],
        env=env
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments=args)
            return str(result.content)

@tool("Get Git Diff")
def get_git_diff(targetPath: str, baseBranch: str = "main") -> str:
    """Get a list of exactly which files changed compared to a base branch. Crucial for limiting context."""
    return asyncio.run(_execute_mcp_tool("get_git_diff", {"targetPath": targetPath, "baseBranch": baseBranch}))

@tool("Read Source File")
def read_source_file(cwd: str, filePath: str) -> str:
    """Read the raw string payload of a specific file so the LLM can extract schemas/logic."""
    return asyncio.run(_execute_mcp_tool("read_source_file", {"cwd": cwd, "filePath": filePath}))

@tool("Database Introspector")
def database_introspector(tables: list[str] = None) -> str:
    """Introspect the Supabase Postgres database. Can be filtered by table names."""
    args = {"tables": tables} if tables else {}
    return asyncio.run(_execute_mcp_tool("database_introspector", args))

@tool("Get Dependency Graph")
def get_dependency_graph(cwd: str, focusFile: str) -> str:
    """Map the 'blast radius' by finding all files that import this focusFile downstream."""
    return asyncio.run(_execute_mcp_tool("get_dependency_graph", {"cwd": cwd, "focusFile": focusFile}))

@tool("Read OpenAPI Route")
def read_openapi_route(cwd: str, openapiPath: str, routePath: str, method: str) -> str:
    """Target a specific route inside a giant Swagger/OpenAPI YAML without loading the whole file."""
    return asyncio.run(_execute_mcp_tool("read_openapi_route", {
        "cwd": cwd, 
        "openapiPath": openapiPath, 
        "routePath": routePath, 
        "method": method
    }))
