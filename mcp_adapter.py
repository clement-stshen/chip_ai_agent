"""Adapter over an MCP server exposing the Verdi-style skills as tools.

Two client implementations, SDK-first:

  - SDK mode (primary): a persistent MCP Python SDK v2 `Client` session
    (legacy protocol handshake) served from a background asyncio loop —
    standard capability negotiation, standard error surfaces, typed results.
  - Legacy mode (fallback): the original zero-dependency stdio JSON-RPC
    client (select() + manual line splitting) — used when the SDK is not
    importable, the server does not speak clean MCP (startup banners etc.),
    or the SDK session fails; it restarts a crashed server on the next call.

Degrades gracefully:
  - no server configured -> calls return an error, the planning loop still works;
  - server that does not speak MCP -> SDK handshake fails, we fall back to the
    legacy raw tools/call mode (previous behavior);
  - server that dies mid-session -> process is torn down and respawned on the
    next call.

Transport note (legacy): the pipe is read in binary unbuffered mode with
select(). Mixing select with a TextIOWrapper is unsafe (readline() may buffer
several messages, after which select reports the fd as empty), so lines are
split manually from raw reads.
"""

from __future__ import annotations

import asyncio
import json
import os
import select
import subprocess
import threading
import time

try:  # SDK presence is optional: without it the adapter is stdlib-only.
    from mcp import Client, StdioServerParameters
    _SDK_IMPORTABLE = True
except ImportError:                                   # pragma: no cover
    _SDK_IMPORTABLE = False


def _sdk_result_to_dict(r) -> dict:
    """CallToolResult -> the legacy adapter result shape.

    Keeps {"content": [...], "isError": bool} so downstream consumers are
    unchanged, and adds "error" on failures so the agent's `"error" not in
    res` step check actually sees remote failures. (v2 types are snake_case.)
    """
    texts = [b.text for b in r.content if getattr(b, "type", None) == "text"]
    out = {"content": [{"type": "text", "text": t} for t in texts],
           "isError": bool(r.is_error)}
    if r.is_error:
        out["error"] = "\n".join(texts)
    return out


class _SdkBridge:
    """Persistent SDK v2 client session on a background asyncio loop.

    Supports BOTH transports: stdio (command list + optional env) and
    streamable-http (url). The legacy select()-based client covers stdio
    only; url mode therefore requires the SDK importable.
    """

    def __init__(self, command: list[str] | None, timeout: float,
                 env: dict | None = None, url: str | None = None):
        self._command = command
        self._url = url
        self._env = env
        self._timeout = timeout
        self._loop: asyncio.AbstractEventLoop | None = None
        self._client = None
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._init_err: Exception | None = None
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="mcp-sdk-adapter")
        self._thread.start()
        if not self._ready.wait(timeout=timeout):
            self._dispose()
            raise RuntimeError("SDK client handshake timed out")
        if self._init_err is not None:
            self._dispose()
            raise self._init_err

    def _dispose(self) -> None:
        """Best-effort cleanup after a failed init: signal the idle loop and
        drop the (possibly half-entered) client so the subprocess exits."""
        self._stop.set()
        try:
            if self._loop is not None and self._client is not None:
                asyncio.run_coroutine_threadsafe(
                    self._client.__aexit__(None, None, None), self._loop)
        except Exception:
            pass
        self._thread.join(timeout=1)

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._main())
        except Exception as e:                        # handshake/parse failure
            self._init_err = e
        finally:
            self._ready.set()

    async def _main(self) -> None:
        if self._url:
            # streamable-http transport (stateful; auto-negotiates protocol)
            client = Client(self._url, read_timeout_seconds=self._timeout)
        else:
            params = StdioServerParameters(command=self._command[0],
                                           args=self._command[1:],
                                           env=self._env)
            # mode="legacy": classic 2024-11-05 initialize handshake (no
            # server/discover probe) — the external Synopsys servers are v1-era.
            client = Client(params, mode="legacy",
                            read_timeout_seconds=self._timeout)
        await client.__aenter__()
        self._client = client
        self._ready.set()
        # idle asynchronously: a blocking threading.Event.wait here would
        # starve the loop and hang every scheduled tools/call coroutine.
        while not self._stop.is_set():
            await asyncio.sleep(0.1)
        await client.__aexit__(None, None, None)
        self._client = None

    def call(self, tool: str, args: dict | None) -> dict:
        assert self._loop is not None and self._client is not None
        fut = asyncio.run_coroutine_threadsafe(
            self._client.call_tool(tool, args or {}), self._loop)
        return _sdk_result_to_dict(fut.result(timeout=self._timeout))

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)


class McpAdapter:
    def __init__(self, command: list[str] | None = None, timeout: float = 30.0,
                 env: dict | None = None, url: str | None = None):
        self.command = command
        self.url = url
        self.env = env
        self.timeout = timeout
        self.proc: subprocess.Popen | None = None
        self._mcp_mode = False
        self._next_id = 1
        self._buf = b""
        self._sdk: _SdkBridge | None = None
        self._sdk_tried = False

    # -- dispatch (SDK first, legacy fallback) --------------------------------
    def call(self, tool: str, args: dict | None = None) -> dict:
        if not self.command and not self.url:
            return {"error": "no MCP server configured (use --server CMD...)",
                    "tool": tool}
        if not self._sdk_tried:
            self._sdk_tried = True
            if _SDK_IMPORTABLE:
                try:
                    self._sdk = _SdkBridge(self.command, self.timeout,
                                           env=self.env, url=self.url)
                except Exception:
                    self._sdk = None
        if self._sdk is not None:
            try:
                return self._sdk.call(tool, args)
            except Exception:
                # server crashed / timed out mid-session: dispose and let the
                # legacy path respawn fresh on this call
                self._sdk.close()
                self._sdk = None
        return self._legacy_call(tool, args)

    # -- legacy transport ------------------------------------------------------
    def _send(self, obj: dict) -> None:
        assert self.proc is not None and self.proc.stdin is not None
        self.proc.stdin.write((json.dumps(obj) + "\n").encode())
        self.proc.stdin.flush()

    def _recv_line(self, timeout: float) -> bytes | None:
        """One raw line from the pipe; None on timeout/EOF."""
        assert self.proc is not None and self.proc.stdout is not None
        fd = self.proc.stdout.fileno()
        deadline = time.monotonic() + timeout
        while b"\n" not in self._buf:
            remain = deadline - time.monotonic()
            if remain <= 0:
                return None  # timeout
            ready, _, _ = select.select([fd], [], [], remain)
            if not ready:
                continue
            chunk = os.read(fd, 65536)
            if not chunk:
                return None  # EOF: server exited
            self._buf += chunk
        line, _, self._buf = self._buf.partition(b"\n")
        return line

    def _recv(self, timeout: float | None = None) -> dict | None:
        """Next JSON message, skipping non-JSON noise lines (banners, logs).

        A single malformed stdout line previously aborted the whole call and
        tore down the transport; servers commonly print startup banners.
        Keep reading until a JSON object arrives, the deadline expires or the
        pipe reaches EOF — only then return None.
        """
        deadline = time.monotonic() + (self.timeout if timeout is None else timeout)
        while True:
            remain = deadline - time.monotonic()
            if remain <= 0:
                return None
            line = self._recv_line(remain)
            if not line:                      # timeout or EOF
                return None
            if not line.strip():
                continue
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue                       # noise line: skip, keep stream

    # -- legacy lifecycle ------------------------------------------------------
    def _spawn(self) -> None:
        self.proc = subprocess.Popen(
            self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,   # server logs must not reach our stdout
            bufsize=0,  # binary unbuffered: select-safe manual line splitting
            env={**os.environ, **(self.env or {})},
        )
        self._buf = b""

    def _teardown(self) -> None:
        if self.proc is not None:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=2)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
        self.proc = None
        self._mcp_mode = False
        self._buf = b""

    def _ensure(self) -> None:
        if not self.command or self.proc is not None:
            return
        # 1) try the standard MCP handshake
        try:
            self._spawn()
            self._send({"jsonrpc": "2.0", "id": 0, "method": "initialize",
                        "params": {"protocolVersion": "2024-11-05",
                                   "capabilities": {},
                                   "clientInfo": {"name": "chip-ai-agent",
                                                  "version": "2.0.0"}}})
            resp = self._recv()
            if resp and resp.get("id") == 0 and "result" in resp:
                self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
                self._mcp_mode = True
                return
        except Exception:
            pass
        # 2) handshake failed: restart fresh and fall back to legacy mode
        self._teardown()
        try:
            self._spawn()
        except Exception:
            self.proc = None

    def _legacy_call(self, tool: str, args: dict | None = None) -> dict:
        """JSON-RPC tools/call over stdio (legacy client, noise-tolerant)."""
        self._ensure()
        if self.proc is None:
            return {"error": "no MCP server configured (use --server CMD...)", "tool": tool}
        req_id = self._next_id
        self._next_id += 1
        req = {
            "jsonrpc": "2.0", "id": req_id, "method": "tools/call",
            "params": {"name": tool, "arguments": args or {}},
        }
        try:
            self._send(req)
            deadline = time.monotonic() + self.timeout
            while time.monotonic() < deadline:
                msg = self._recv(timeout=deadline - time.monotonic())
                if msg is None:
                    break  # timeout/EOF -> report and restart next call
                if msg.get("id") == req_id:
                    if "result" in msg:
                        return msg["result"]
                    return {"error": json.dumps(msg.get("error")), "tool": tool}
                # legacy servers reply without id (previous behavior)
                if not self._mcp_mode and "id" not in msg:
                    return msg
                # otherwise: server notification -> skip and keep waiting
            # no matching response: treat as failure and respawn on next call
            self._teardown()
            return {"error": "mcp call timed out or server exited", "tool": tool}
        except Exception as e:
            self._teardown()
            return {"error": f"mcp call failed: {e}", "tool": tool}

    def close(self):
        if self._sdk is not None:
            self._sdk.close()
            self._sdk = None
        self._teardown()
