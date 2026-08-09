import asyncio

ALLOWED_HOSTS = frozenset(
    {
        # GitHub (git, API, raw, release assets)
        "github.com",
        "api.github.com",
        "codeload.github.com",
        "raw.githubusercontent.com",
        "objects.githubusercontent.com",
        "uploads.github.com",
        "githubassets.com",
        # PyPI (pip)
        "pypi.org",
        "www.pypi.org",
        "files.pythonhosted.org",
        "pypi.io",
        # npm
        "registry.npmjs.org",
        "www.npmjs.com",
        "npmjs.org",
        "nodejs.org",
    }
)

BLOCKED = (
    b"HTTP/1.1 403 Forbidden\r\n"
    b"Connection: close\r\n"
    b"Content-Length: 15\r\n"
    b"\r\n"
    b"access denied\n"
)


def log(msg: str) -> None:
    print(msg, flush=True)


def allowed(host: str) -> bool:
    return host.lower() in ALLOWED_HOSTS


async def pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, idle_s: float = 120.0) -> None:
    try:
        while True:
            data = await asyncio.wait_for(reader.read(65536), timeout=idle_s)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except (asyncio.TimeoutError, ConnectionError, OSError):
        pass
    finally:
        try:
            writer.close()
        except OSError:
            pass


async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    peer = writer.get_extra_info("peername")
    try:
        request_line = await asyncio.wait_for(reader.readline(), timeout=10)
        if not request_line:
            writer.close()
            return
        parts = request_line.decode("latin1", "replace").strip().split(" ")
        if len(parts) < 3:
            writer.close()
            return
        method, target = parts[0], parts[1]
        while True:
            line = await asyncio.wait_for(reader.readline(), timeout=10)
            if line in (b"\r\n", b"\n", b""):
                break

        if method == "CONNECT":
            host, _, port = target.rpartition(":")
            try:
                port = int(port or 443)
            except ValueError:
                writer.close()
                return
            if not allowed(host):
                log(f"BLOCK {peer} CONNECT {target}")
                writer.write(BLOCKED)
                await writer.drain()
                writer.close()
                return
            log(f"ALLOW {peer} CONNECT {target}")
            up_reader, up_writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=10)
            writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
            await writer.drain()
            await asyncio.gather(pipe(reader, up_writer), pipe(up_reader, writer))
        elif method in ("GET", "POST", "HEAD", "PUT", "DELETE"):
            scheme, rest = target.split("://", 1)
            hostport, _, path = rest.partition("/")
            host, _, port = hostport.rpartition(":")
            try:
                port = int(port or 80)
            except ValueError:
                writer.close()
                return
            if not allowed(host):
                log(f"BLOCK {peer} {method} {target}")
                writer.write(BLOCKED)
                await writer.drain()
                writer.close()
                return
            log(f"ALLOW {peer} {method} {target}")
            up_reader, up_writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=10)
            request = f"{method} /{path} HTTP/1.1\r\nHost: {hostport}\r\nConnection: close\r\n\r\n"
            up_writer.write(request.encode())
            await up_writer.drain()
            await asyncio.gather(pipe(up_reader, writer), pipe(reader, up_writer))
        else:
            writer.close()
    except Exception as e:
        log(f"ERROR {peer} {e!r}")
        try:
            writer.close()
        except OSError:
            pass


async def main() -> None:
    server = await asyncio.start_server(handle, "0.0.0.0", 8888)
    log(f"egress proxy on 0.0.0.0:8888, allowlist={len(ALLOWED_HOSTS)} hosts")
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
