"""Where an address typed or spoken to the Hub may point.

An address that reaches the Hub through Talk, a mission or a web form is chosen by a person or a model, and a downloader or `git clone`
will follow it wherever it leads - to the router's admin page, another machine on the LAN, this PC's own services (including the Hub),
or a cloud metadata endpoint. `check_url` refuses those before anything is fetched. A path on this PC is a different input and is
handled by its caller.

Limits, stated plainly: the name is looked up once here and the fetching tool looks it up again, so a hostile DNS server could answer
differently the second time. Closing that needs the fetch itself to run through a checked connection; the downloader and git do their own.
"""
from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from urllib.parse import urlsplit

_METADATA_NAMES = {"localhost", "metadata.google.internal", "metadata", "instance-data"}
_NUMERIC = re.compile(r"(?:0x[0-9a-f]+|\d+)(?:\.(?:0x[0-9a-f]+|\d+)){0,3}", re.I)
_SCP = re.compile(r"^[\w.-]+@([\w.-]+):")           # git@github.com:owner/repo.git


def host_of(url: str) -> str:
    """The host in an http(s):// or ssh-style git address, lower case, or '' when there is none."""
    url = (url or "").strip()
    m = _SCP.match(url)
    if m:
        return m.group(1).lower()
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def _public(ip: str) -> bool:
    a = ipaddress.ip_address(ip.split("%")[0])
    if isinstance(a, ipaddress.IPv6Address) and a.ipv4_mapped:
        a = a.ipv4_mapped
    return a.is_global


def _resolve(host: str) -> "list[str]":
    try:
        return sorted({i[4][0] for i in socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)})
    except socket.gaierror:
        return []


def check_host(host: str, resolver=_resolve) -> None:
    """Raises ValueError unless every address `host` points to is a public one. A name that does not resolve passes: there is nothing to reach."""
    host = (host or "").strip("[]").lower().rstrip(".")
    if not host:
        raise ValueError("that address has no host name")
    if host in _METADATA_NAMES or host.endswith((".localhost", ".internal", ".local")):
        raise ValueError(f"{host} is a name for this machine or its network, not a public site")
    if _NUMERIC.fullmatch(host):                       # 2130706433, 0x7f.1, 017700000001: the old spellings of an IPv4 address
        try:
            host = socket.inet_ntoa(socket.inet_aton(host))
        except OSError:
            raise ValueError(f"{host} is not an address I can check") from None
    try:
        ipaddress.ip_address(host)
        ips = [host]
    except ValueError:
        ips = resolver(host)
    for ip in ips:
        if not _public(ip):
            raise ValueError(f"{host} points to {ip}, an address on this machine or its network, not a public site")


def check_url(url: str, resolver=_resolve) -> None:
    """Raises ValueError for an address that is not http(s)/ssh git form or whose host is not public."""
    host = host_of(url)
    if not (url or "").strip().lower().startswith(("http://", "https://")) and not _SCP.match((url or "").strip()):
        raise ValueError("only http(s):// and git@ addresses are allowed")
    check_host(host, resolver)


async def acheck_url(url: str, resolver=_resolve) -> None:
    """check_url without blocking the event loop on the name lookup."""
    await asyncio.get_running_loop().run_in_executor(None, lambda: check_url(url, resolver))
