#!/usr/bin/env python3
"""
DumbOLT for Cdata — EPON monitor & ONU management (backend)

Stage 2.5: Dashboard drill-down lists + name retry loop.

New in this version:
- /dashboard now returns lists per bucket (online/offline/warning/critical/new_24h)
- new_onus.txt lines include a name= field
- Background name retry loop (default 60s) — resolves empty ONU names
  from mac_address.txt via learned MACs, writes to onu_names.json
- name_updates.txt — append-only log of every name resolved by the retry
- /names/retry-now, /names/retry-status, /names/updates endpoints

Run:  python3 2_DumbOLT.py
Docs: http://<host>:<api_port>/docs
"""

import asyncio
import json
import os
import re
import socket
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


# ============================================================
# PATH RESOLUTION
# ============================================================
SCRIPT_DIR    = os.path.dirname(os.path.abspath(__file__))
NET_DATA_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "net_data"))


def _resolve_bts_config() -> str:
    candidates = [
        os.path.join(NET_DATA_ROOT, "bts_config.json"),
        os.path.join(SCRIPT_DIR,    "bts_config.json"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    raise FileNotFoundError(
        "bts_config.json not found. Looked in:\n  " + "\n  ".join(candidates)
    )


def _resolve_script_file(name: str) -> str:
    return os.path.join(SCRIPT_DIR, name)


BTS_CONFIG_PATH   = _resolve_bts_config()
CDATA_CONFIG_PATH = _resolve_script_file("cdata_config.json")
NEW_ONUS_FILE     = _resolve_script_file("new_onus.txt")
MAC_ADDRESS_FILE  = _resolve_script_file("mac_address.txt")


# ============================================================
# CONFIG LOADING
# ============================================================
with open(CDATA_CONFIG_PATH, "r", encoding="utf-8") as f:
    CDATA_CONFIG = json.load(f)

CDATA_USERNAME = CDATA_CONFIG.get("cdata_credentials", {}).get("username", "admin")
CDATA_PASSWORD = CDATA_CONFIG.get("cdata_credentials", {}).get("password", "admin123")
CDATA_PORTS    = CDATA_CONFIG.get("ports", [1, 2, 3, 4, 5, 6, 7, 8])

API_PORT       = int(CDATA_CONFIG.get("api_port", 8310))
CORS_ORIGINS   = CDATA_CONFIG.get("cors_origins", []) or []

_auto_scan_cfg = CDATA_CONFIG.get("auto_scan", {}) or {}
AUTO_SCAN_ENABLED  = bool(_auto_scan_cfg.get("enabled", False))
AUTO_SCAN_INTERVAL = int(_auto_scan_cfg.get("interval_seconds", 1200))

_alarms_cfg = CDATA_CONFIG.get("alarms", {}) or {}
ALARMS_ENABLED  = bool(_alarms_cfg.get("enabled", True))
ALARM_LOG_NAME  = _alarms_cfg.get("log_file", "alarm_log.txt")
ALARM_BACKOFF   = _alarms_cfg.get("reconnect_backoff_seconds", [5, 10, 30, 60]) or [5, 10, 30, 60]
ALARM_LOG_FILE  = _resolve_script_file(ALARM_LOG_NAME)
OFFLINE_GRACE_SECONDS = int(_alarms_cfg.get("offline_grace_seconds", 30))

_names_cfg = CDATA_CONFIG.get("names", {}) or {}
NAME_RETRY_INTERVAL = int(_names_cfg.get("retry_interval_seconds", 60))
NAME_UPDATES_NAME   = _names_cfg.get("updates_log", "name_updates.txt")
NAME_UPDATES_FILE   = _resolve_script_file(NAME_UPDATES_NAME)

_dash_cfg = CDATA_CONFIG.get("dashboard", {}) or {}
DASH_REFRESH_INTERVAL   = int(_dash_cfg.get("refresh_interval_seconds", 15))
SIGNAL_WARNING_DBM      = float(_dash_cfg.get("signal_warning_dbm", -24))
SIGNAL_CRITICAL_DBM     = float(_dash_cfg.get("signal_critical_dbm", -27))
PON_OUTAGE_PARTIAL      = float(_dash_cfg.get("pon_outage_partial_ratio", 0.5))
PON_OUTAGE_MIN_ONUS     = int(_dash_cfg.get("pon_outage_min_onus_ever", 2))
DASH_LIST_LIMIT         = int(_dash_cfg.get("list_limit", 200))

_save_file_raw = CDATA_CONFIG.get("cdata_save_file", "onu_status.json")
SAVE_FILE = _save_file_raw if os.path.isabs(_save_file_raw) else _resolve_script_file(_save_file_raw)

_save_dir = os.path.dirname(SAVE_FILE) or SCRIPT_DIR
NAMES_FILE = os.path.join(_save_dir, "onu_names.json")

with open(BTS_CONFIG_PATH, "r", encoding="utf-8") as f:
    BTS_CONFIG = json.load(f)


def _is_cdata_site(site: Dict) -> bool:
    olt_type = str(site.get("olt_type", "")).lower()
    return "cdata" in olt_type and bool(site.get("olt_ip"))


CDATA_OLT_DEVICES: Dict[str, Dict[str, str]] = {}
for _site in BTS_CONFIG.get("bts_sites", []):
    if not _is_cdata_site(_site):
        continue
    _name = _site.get("name", "Unnamed")
    CDATA_OLT_DEVICES[_name] = {
        "name": _name,
        "ip":   _site["olt_ip"],
    }


# ============================================================
# IN-MEMORY STATE
# ============================================================
# ============================================================
# EXCEPTIONS
# ============================================================
class OltUnreachableError(Exception):
    """Raised when a Telnet connection to the OLT cannot be established
    at all (TCP refused / timeout / network unreachable)."""
    def __init__(self, host: str, reason: str = ""):
        self.host = host
        self.reason = reason
        super().__init__(f"OLT {host} unreachable: {reason}")


_results_cache: Dict[str, Dict[str, List[Dict]]] = {}
_olt_locks: Dict[str, asyncio.Lock] = {name: asyncio.Lock() for name in CDATA_OLT_DEVICES}
_locks_guard = asyncio.Lock()
_file_write_lock = asyncio.Lock()


async def get_olt_lock(olt_name: str) -> asyncio.Lock:
    async with _locks_guard:
        if olt_name not in _olt_locks:
            _olt_locks[olt_name] = asyncio.Lock()
        return _olt_locks[olt_name]


_auto_scan_task: Optional[asyncio.Task] = None
_auto_scan_state = {
    "enabled":     AUTO_SCAN_ENABLED,
    "interval":    AUTO_SCAN_INTERVAL,
    "last_run":    None,
    "next_run":    None,
    "last_result": {},
    "running":     False,
}

_name_retry_task: Optional[asyncio.Task] = None
_name_retry_state = {
    "interval":         NAME_RETRY_INTERVAL,
    "last_run":         None,
    "next_run":         None,
    "last_resolved":    0,
    "last_scanned":     0,
    "total_resolved":   0,
    "running":          False,
}


# ============================================================
# SMALL UTILITIES
# ============================================================
def _norm_mac(m: str) -> str:
    return (m or "").lower().replace(":", "").replace("-", "")


def _pretty_mac(m: str) -> str:
    n = _norm_mac(m)
    if len(n) != 12:
        return (m or "").lower()
    return ":".join(n[i:i+2] for i in range(0, 12, 2))


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ============================================================
# PPP SESSION DUMP — mac_address.txt
# ============================================================
_ppp_map: Dict[str, str] = {}
_ppp_loaded_at: Optional[str] = None
_ppp_source_lines: int = 0


def load_ppp_sessions(path: str = MAC_ADDRESS_FILE) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not os.path.exists(path):
        return out
    name_re  = re.compile(r"(?:^|\s)name=(\S+)",      re.IGNORECASE)
    caller_re = re.compile(r"(?:^|\s)caller-id=(\S+)", re.IGNORECASE)
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                m_name   = name_re.search(line)
                m_caller = caller_re.search(line)
                if not (m_name and m_caller):
                    continue
                name = m_name.group(1).strip()
                mac  = _norm_mac(m_caller.group(1).strip())
                if len(mac) != 12:
                    continue
                out[mac] = name
    except Exception as e:
        print(f"[PPP] Error loading {path}: {e}")
    return out


def refresh_ppp_sessions() -> int:
    global _ppp_map, _ppp_loaded_at, _ppp_source_lines
    _ppp_map = load_ppp_sessions()
    _ppp_loaded_at = _now_str()
    try:
        with open(MAC_ADDRESS_FILE, "r", encoding="utf-8", errors="ignore") as f:
            _ppp_source_lines = sum(1 for _ in f)
    except Exception:
        _ppp_source_lines = 0
    return len(_ppp_map)


def resolve_name_from_learned(learned_macs: List[str]) -> Optional[Tuple[str, str]]:
    """
    Return (name, matched_learned_mac) or None. First match wins,
    iterating learned MACs in sorted order for determinism.
    """
    if not learned_macs:
        return None
    for lm in sorted(learned_macs, key=_norm_mac):
        name = _ppp_map.get(_norm_mac(lm))
        if name:
            return name, lm
    return None


# ============================================================
# ONU NAMES FILE
# ============================================================
def _migrate_names(raw: Dict) -> Dict[str, Dict]:
    out: Dict[str, Dict] = {}
    for k, v in raw.items():
        key = _pretty_mac(k)
        if isinstance(v, str):
            out[key] = {"name": v, "source": "manual", "updated_at": _now_str()}
        elif isinstance(v, dict):
            out[key] = {
                "name": v.get("name", "") or "",
                "source": v.get("source", "manual") or "manual",
                "updated_at": v.get("updated_at") or _now_str(),
            }
    return out


def load_onu_names() -> Dict[str, Dict]:
    try:
        if not os.path.exists(NAMES_FILE):
            return {}
        with open(NAMES_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            return {}
        return _migrate_names(raw)
    except Exception as e:
        print(f"[NAMES] Error loading {NAMES_FILE}: {e}")
        return {}


def _save_names(mapping: Dict[str, Dict]) -> bool:
    try:
        tmp = NAMES_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(mapping, f, indent=2, sort_keys=True)
        os.replace(tmp, NAMES_FILE)
        return True
    except Exception as e:
        print(f"[NAMES] Error writing {NAMES_FILE}: {e}")
        return False


def upsert_name(mac: str, name: str, source: str = "manual") -> bool:
    existing = load_onu_names()
    key = _pretty_mac(mac)
    if not key:
        return False
    current = existing.get(key)
    if current and current.get("source") == "manual" and source == "auto":
        return False
    if not name:
        if source == "manual" and key in existing:
            existing.pop(key, None)
            return _save_names(existing)
        return False
    existing[key] = {"name": name, "source": source, "updated_at": _now_str()}
    return _save_names(existing)


def enrich_with_names(ports_data: Dict[str, List[Dict]]) -> Dict[str, List[Dict]]:
    names = load_onu_names()
    if not names:
        return ports_data
    out: Dict[str, List[Dict]] = {}
    for port_str, onus in ports_data.items():
        enriched_list = []
        for onu in onus:
            new_onu = dict(onu)
            key = _pretty_mac(new_onu.get("Mac address", ""))
            entry = names.get(key)
            if entry and entry.get("name"):
                new_onu["Name"] = entry["name"]
            enriched_list.append(new_onu)
        out[port_str] = enriched_list
    return out


def enrich_single_onu(onu: Dict) -> Dict:
    names = load_onu_names()
    if not names:
        return onu
    new_onu = dict(onu)
    key = _pretty_mac(new_onu.get("Mac address", ""))
    entry = names.get(key)
    if entry and entry.get("name"):
        new_onu["Name"] = entry["name"]
    return new_onu


# ============================================================
# PERSISTENCE
# ============================================================
def ensure_onu_status_file() -> None:
    if not os.path.exists(SAVE_FILE):
        try:
            with open(SAVE_FILE, "w", encoding="utf-8") as f:
                json.dump({}, f, indent=2)
            print(f"[SAVE] Created empty {SAVE_FILE}")
        except Exception as e:
            print(f"[SAVE] Could not create {SAVE_FILE}: {e}")


def load_previous_results() -> Dict:
    try:
        if os.path.exists(SAVE_FILE):
            with open(SAVE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"[SAVE] Error loading previous results: {e}")
    return {}


def save_results(results: Dict) -> bool:
    try:
        tmp = SAVE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        os.replace(tmp, SAVE_FILE)
        return True
    except Exception as e:
        print(f"[SAVE] Error saving: {e}")
        return False


# ============================================================
# NEW ONU DISCOVERY LOG
# ============================================================
_NEW_ONUS_HEADER = (
    "# New ONU discovery log — DumbOLT for Cdata\n"
    "# Format: timestamp | OLT=<name> (<ip>) | port=<n> | onu_id=<id> | "
    "mac=<mac> | name=<name-or-?> | signal=<signal>\n"
)


def ensure_new_onus_file() -> None:
    if not os.path.exists(NEW_ONUS_FILE):
        try:
            with open(NEW_ONUS_FILE, "w", encoding="utf-8") as f:
                f.write(_NEW_ONUS_HEADER)
        except Exception as e:
            print(f"[LOG] Could not create {NEW_ONUS_FILE}: {e}")


def log_new_onu(olt_name: str, olt_ip: str, port: int, onu: Dict) -> None:
    try:
        ensure_new_onus_file()
        name = onu.get("Name") or "?"
        line = (
            f"{_now_str()} | OLT={olt_name} ({olt_ip}) | port={port} | "
            f"onu_id={onu.get('ID', '?')} | mac={onu.get('Mac address', '?')} | "
            f"name={name} | signal={onu.get('Onu signal', 'N/A')}\n"
        )
        with open(NEW_ONUS_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception as e:
        print(f"[LOG] Error writing discovery log: {e}")


# ============================================================
# NAME UPDATES LOG
# ============================================================
_NAME_UPDATES_HEADER = (
    "# ONU name updates — DumbOLT for Cdata\n"
    "# Format: resolved_at | OLT=<name> (<ip>) | port=<n> | onu_id=<id> | "
    "mac=<onu_mac> | name=<resolved> | via=<learned_mac> | source=<auto|manual>\n"
)


def ensure_name_updates_file() -> None:
    if not os.path.exists(NAME_UPDATES_FILE):
        try:
            with open(NAME_UPDATES_FILE, "w", encoding="utf-8") as f:
                f.write(_NAME_UPDATES_HEADER)
            print(f"[NAME-LOG] Created {NAME_UPDATES_FILE}")
        except Exception as e:
            print(f"[NAME-LOG] Could not create {NAME_UPDATES_FILE}: {e}")


def append_name_update(olt_name: str, olt_ip: str, port: Optional[int],
                       onu_id: Optional[str], onu_mac: str,
                       resolved_name: str, via_mac: str,
                       source: str) -> None:
    try:
        ensure_name_updates_file()
        line = (
            f"{_now_str()} | OLT={olt_name} ({olt_ip}) | "
            f"port={port if port is not None else '?'} | "
            f"onu_id={onu_id if onu_id is not None else '?'} | "
            f"mac={onu_mac} | name={resolved_name} | via={via_mac} | source={source}\n"
        )
        with open(NAME_UPDATES_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception as e:
        print(f"[NAME-LOG] Error appending: {e}")


# ============================================================
# ALARM LOG
# ============================================================
_ALARM_LOG_HEADER = (
    "# OLT alarm log — DumbOLT for Cdata\n"
    "# Format: our_time | OLT=<name> (<ip>) | port=<n> | onu_id=<id> | "
    "state=<online|offline> | mac=<mac or ?> | raw=<original line>\n"
)


def ensure_alarm_log_file() -> None:
    if not os.path.exists(ALARM_LOG_FILE):
        try:
            with open(ALARM_LOG_FILE, "w", encoding="utf-8") as f:
                f.write(_ALARM_LOG_HEADER)
            print(f"[ALARM-LOG] Created {ALARM_LOG_FILE}")
        except Exception as e:
            print(f"[ALARM-LOG] Could not create {ALARM_LOG_FILE}: {e}")


def append_alarm_log(olt_name: str, olt_ip: str, port: Optional[int],
                     onu_id: Optional[str], state: Optional[str],
                     mac: Optional[str], raw: str) -> None:
    try:
        ensure_alarm_log_file()
        line = (
            f"{_now_str()} | OLT={olt_name} ({olt_ip}) | "
            f"port={port if port is not None else '?'} | "
            f"onu_id={onu_id if onu_id is not None else '?'} | "
            f"state={state or '?'} | mac={mac or '?'} | raw={raw.strip()}\n"
        )
        with open(ALARM_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception as e:
        print(f"[ALARM-LOG] Error appending: {e}")


# ============================================================
# TELNET HELPERS
# ============================================================
def _split_host_port(host: str, default_port: int = 23) -> Tuple[str, int]:
    host = str(host).strip()
    if ":" in host and host.count(":") <= 2:
        h, p = host.rsplit(":", 1)
        return h, int(p)
    return host, default_port


async def _read_until(reader, marker: bytes, timeout: float = 10.0) -> bytes:
    return await asyncio.wait_for(reader.readuntil(marker), timeout=timeout)


async def telnet_login(reader, writer, username: str, password: str) -> None:
    await _read_until(reader, b"Username:", timeout=10)
    writer.write((username + "\r\n").encode()); await writer.drain()
    await _read_until(reader, b"Password:", timeout=10)
    writer.write((password + "\r\n").encode()); await writer.drain()
    await asyncio.sleep(1)
    try:
        await asyncio.wait_for(reader.read(4096), timeout=1)
    except asyncio.TimeoutError:
        pass


async def get_full_command_output(reader, writer, command: str, max_pages: int = 10) -> str:
    full_output = ""
    writer.write((command + "\r\n").encode())
    await writer.drain()
    for _ in range(max_pages):
        await asyncio.sleep(1)
        try:
            chunk = await asyncio.wait_for(reader.read(4096), timeout=2)
            if not chunk:
                break
            text = chunk.decode("utf-8", errors="ignore")
            full_output += text
            if "epon#" in text or "#" in text or ">" in text:
                break
        except asyncio.TimeoutError:
            pass
    return full_output


async def get_onu_signal(reader, writer, port: int, onu_id: str) -> str:
    try:
        command = f"show olt {port} onu {onu_id} ctc optical"
        output = await get_full_command_output(reader, writer, command)
        match = re.search(r"rx power\s+(-?\d+\.\d+)\s*d?Bm?", output, re.IGNORECASE)
        if match:
            return match.group(1) + " dBm"
        return "N/A"
    except Exception:
        return "N/A"


async def get_mac_address_table(reader, writer, port: int) -> Dict[str, List[str]]:
    onu_macs: Dict[str, List[str]] = defaultdict(list)
    try:
        writer.write(f"show olt {port} mac-address-table\r\n".encode())
        await writer.drain()
        full_output = ""
        for _ in range(50):
            await asyncio.sleep(0.5)
            try:
                chunk = await asyncio.wait_for(reader.read(8192), timeout=2)
                if not chunk:
                    break
                text = chunk.decode("utf-8", errors="ignore")
                full_output += text
                if "Press any key to continue" in text or "--More--" in text:
                    writer.write(b" "); await writer.drain(); await asyncio.sleep(0.5)
                    continue
                if "Entries Found" in text:
                    await asyncio.sleep(0.3)
                    try:
                        final = await asyncio.wait_for(reader.read(4096), timeout=1)
                        if final:
                            full_output += final.decode("utf-8", errors="ignore")
                    except asyncio.TimeoutError:
                        pass
                    break
            except asyncio.TimeoutError:
                break
        full_output = full_output.replace("Press any key to continue (Q to quit)", "")
        full_output = full_output.replace("Press any key to continue", "")
        full_output = full_output.replace("(Q to quit)", "")
        for line in full_output.split("\n"):
            line = line.strip()
            if not line:
                continue
            if any(x in line for x in [
                "Index", "MAC Address", "=====", "MAC Address Table",
                "Entries Found", "SLOT", "EVT_OAM_ALERT", "Dying Gasp",
                "show olt", "epon#",
            ]):
                continue
            parts = line.split()
            if len(parts) >= 4:
                if re.match(
                    r"[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}:"
                    r"[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}",
                    parts[1],
                ):
                    try:
                        int(parts[0])
                        mac_addr = parts[1]
                        onu_id = str(int(parts[2]))
                        onu_macs[onu_id].append(mac_addr)
                        continue
                    except (ValueError, IndexError):
                        pass
                for i, part in enumerate(parts):
                    if re.match(
                        r"[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}:"
                        r"[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}",
                        part,
                    ):
                        mac_addr = part
                        if i + 1 < len(parts):
                            try:
                                onu_id = str(int(parts[i + 1]))
                                onu_macs[onu_id].append(mac_addr)
                            except ValueError:
                                pass
                        break
    except Exception as e:
        print(f"[MAC_TABLE] Error: {e}")
    return dict(onu_macs)


def parse_online_onu(output: str, port: int) -> List[Dict]:
    onu_list: List[Dict] = []
    for line in output.split("\n"):
        line = line.strip()
        if re.match(r"^\d+\s+\d+\s+[0-9a-f:-]{10,}", line.lower()):
            parts = line.split()
            if len(parts) >= 3:
                onu_id = parts[1]
                mac = parts[2].lower().replace("-", ":")
                onu_list.append({"onu_id": onu_id, "mac": mac})
    return onu_list


# ============================================================
# MONITORING (scan)
# ============================================================
async def monitor_olt(host: str, ports: List[int],
                      username: str = CDATA_USERNAME,
                      password: str = CDATA_PASSWORD) -> Dict[str, List[Dict]]:
    results: Dict[str, List[Dict]] = {}
    writer = None
    try:
        h, p = _split_host_port(host, 23)
        print(f"[CDATA] Connecting to {h}:{p}")
        try:
            reader, writer = await asyncio.open_connection(h, p)
        except (ConnectionRefusedError, TimeoutError, OSError) as e:
            raise OltUnreachableError(host, reason=str(e) or type(e).__name__) from e
        await telnet_login(reader, writer, username, password)
        for port in ports:
            full_output = await get_full_command_output(reader, writer, f"show olt online-onu {port}")
            onu_list = parse_online_onu(full_output, port)
            mac_table = await get_mac_address_table(reader, writer, port)
            table_data: List[Dict] = []
            for onu in onu_list:
                onu_id = onu["onu_id"]
                mac    = onu["mac"]
                signal = await get_onu_signal(reader, writer, port, onu_id)
                learned_macs = mac_table.get(onu_id, [])
                if not learned_macs:
                    learned_macs = mac_table.get(str(onu_id).zfill(2), [])
                if not learned_macs:
                    try:
                        learned_macs = mac_table.get(str(int(onu_id)), [])
                    except ValueError:
                        pass
                table_data.append({
                    "Status":       "online",
                    "ID":           onu_id,
                    "Name":         "",
                    "Mac address":  mac,
                    "Onu signal":   signal,
                    "Learned MACs": learned_macs,
                })
            results[str(port)] = table_data
        return results
    except Exception as e:
        print(f"[CDATA] Error monitoring OLT {host}: {e}")
        return {}
    finally:
        if writer:
            try:
                writer.close(); await writer.wait_closed()
            except Exception:
                pass


# ============================================================
# UPSERT
# ============================================================
def upsert_olt_scan(olt_name: str, olt_ip: str,
                    scan: Dict[str, List[Dict]],
                    prev_data: Dict) -> Dict[str, List[Dict]]:
    if olt_ip not in prev_data:
        prev_data[olt_ip] = {}
    merged: Dict[str, List[Dict]] = {}
    now = _now_str()
    for port_str, freshly_scanned in scan.items():
        prev_port_list = prev_data[olt_ip].get(port_str, [])
        prev_by_mac: Dict[str, Dict] = {
            _norm_mac(o.get("Mac address", o.get("mac", ""))): o
            for o in prev_port_list
        }
        seen_macs_this_scan = set()
        out_list: List[Dict] = []
        for fresh in freshly_scanned:
            mac_norm = _norm_mac(fresh.get("Mac address", ""))
            if mac_norm and mac_norm in prev_by_mac:
                rec = prev_by_mac[mac_norm]
                rec["ID"]           = fresh.get("ID", rec.get("ID"))
                rec["Mac address"]  = fresh.get("Mac address", rec.get("Mac address"))
                rec["Status"]       = "online"
                rec["Onu signal"]   = fresh.get("Onu signal", "N/A")
                rec["Learned MACs"] = fresh.get("Learned MACs", [])
                rec["last_seen"]    = now
                rec.setdefault("Name", "")
                if not rec.get("first_seen"):
                    rec["first_seen"] = now
                out_list.append(rec)
                seen_macs_this_scan.add(mac_norm)
            else:
                rec = {
                    "ID":           fresh.get("ID"),
                    "Name":         "",
                    "Mac address":  fresh.get("Mac address"),
                    "Status":       "online",
                    "Onu signal":   fresh.get("Onu signal", "N/A"),
                    "Learned MACs": fresh.get("Learned MACs", []),
                    "first_seen":   now,
                    "last_seen":    now,
                }
                log_new_onu(olt_name, olt_ip, int(port_str), rec)
                out_list.append(rec)
                seen_macs_this_scan.add(mac_norm)
        for mac_norm, prev_rec in prev_by_mac.items():
            if mac_norm in seen_macs_this_scan:
                continue
            prev_rec["Status"] = "offline"
            prev_rec.setdefault("Onu signal", "N/A")
            prev_rec.setdefault("Learned MACs", [])
            prev_rec.setdefault("Name", "")
            if not prev_rec.get("first_seen"):
                prev_rec["first_seen"] = now
            out_list.append(prev_rec)
        merged[port_str] = out_list
        prev_data[olt_ip][port_str] = out_list
    return merged


# ============================================================
# OLT-UNREACHABLE HANDLING
# ============================================================
def mark_all_olt_onus_offline(olt_name: str, olt_ip: str,
                              cause: str = "olt_unreachable",
                              detail: str = "") -> int:
    """
    Flip every ONU for this OLT to Status='offline'.
    Updates onu_status.json and the in-memory cache.
    Returns number of ONUs flipped.
    """
    now = _now_str()
    affected = 0

    data = load_previous_results()
    olt_data = data.get(olt_ip, {})
    for port_str, onus in olt_data.items():
        for onu in onus:
            if onu.get("Status") != "offline":
                affected += 1
            onu["Status"]       = "offline"
            onu["cause"]        = cause
            onu["cause_detail"] = detail
            onu["cause_at"]     = now
    save_results(data)

    if olt_ip in _results_cache:
        for port_str, onus in _results_cache[olt_ip].items():
            for onu in onus:
                onu["Status"]       = "offline"
                onu["cause"]        = cause
                onu["cause_detail"] = detail
                onu["cause_at"]     = now

    return affected


# ============================================================
# REBOOT
# ============================================================
async def reboot_onu(host: str, olt_port: int, onu_id: str,
                     username: str = CDATA_USERNAME,
                     password: str = CDATA_PASSWORD) -> Tuple[bool, str]:
    writer = None
    log: List[str] = []
    try:
        h, p = _split_host_port(host, 23)
        reader, writer = await asyncio.open_connection(h, p)
        banner = await _read_until(reader, b"Username:", timeout=10)
        log.append(banner.decode(errors="ignore"))
        writer.write((username + "\r\n").encode()); await writer.drain()
        await asyncio.sleep(0.5)
        prompt = await _read_until(reader, b"Password:", timeout=10)
        log.append(prompt.decode(errors="ignore"))
        writer.write((password + "\r\n").encode()); await writer.drain()
        await asyncio.sleep(0.5)
        await reader.read(4096)
        writer.write(f"olt {olt_port}\r\n".encode()); await writer.drain()
        await asyncio.sleep(1)
        writer.write(f"onu {onu_id}\r\n".encode()); await writer.drain()
        await asyncio.sleep(1)
        writer.write("ctc reboot\r\n".encode()); await writer.drain()
        await asyncio.sleep(2)
        confirmation = b""
        for _ in range(5):
            try:
                chunk = await asyncio.wait_for(reader.read(4096), timeout=1)
                if not chunk:
                    break
                confirmation += chunk
            except asyncio.TimeoutError:
                break
        text = confirmation.decode(errors="ignore")
        log.append(text)
        if any(k in text.lower() for k in ("please wait", "success", "reboot")):
            log.append("Reboot command sent successfully")
            success = True
        else:
            log.append("Reboot may have failed")
            success = False
        try:
            writer.write(b"exit\r\nexit\r\nexit\r\n"); await writer.drain()
            await asyncio.sleep(1)
        except Exception:
            pass
        return success, "\n".join(log)
    except asyncio.TimeoutError:
        return False, "Timeout: device not responding."
    except Exception as e:
        return False, f"Error: {e}"
    finally:
        if writer:
            try:
                writer.close(); await writer.wait_closed()
            except Exception:
                pass


# ============================================================
# ALARM LISTENER
# ============================================================

# ------------------------------------------------------------
# Alarm cause classification
# ------------------------------------------------------------
# First match wins. Add new entries as new alarm formats are observed.
# Example future entry: ("loss of signal", "los"),
ALARM_CAUSE_MAP = [
    # Order matters — first match wins.
    # 'dying gasp' is the specific power-loss marker.
    # 'offline' is the generic LOSi (loss of signal) event.
    ("dying gasp", "power_loss"),
    ("offline",    "los"),
]


def classify_alarm_cause(raw_line: str) -> str:
    """Return a normalized cause label for an alarm line, or 'unknown'."""
    txt = (raw_line or "").lower()
    for needle, cause in ALARM_CAUSE_MAP:
        if needle in txt:
            return cause
    return "unknown"


_ALARM_RE = re.compile(
    r"onu-(\d+)-(\d+)-(\d+).*?(online|offline)",
    re.IGNORECASE | re.DOTALL,
)
_ALARM_MAC_RE = re.compile(r"mac-([0-9a-fA-F]{2}(?:-[0-9a-fA-F]{2}){5})")


class AlarmListener:
    def __init__(self, olt_name: str, olt_ip: str):
        self.olt_name = olt_name
        self.olt_ip = olt_ip
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()

        self.connected = False
        self.started_at: Optional[str] = None
        self.last_event_at: Optional[str] = None
        self.last_error: Optional[str] = None
        self.events_processed = 0
        self.reconnects = 0

        # Scenario D — OLT-reachability via listener lifecycle
        self._disconnect_grace_task = None
        self._marked_offline        = False
        self._disconnect_started_at = None

    def start(self):
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())

    async def stop(self):
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def restart(self):
        await self.stop()
        self._stop = asyncio.Event()
        self.start()

    # ────────────────────────────────────────────────────────────
    # Scenario D — OLT-reachability via listener lifecycle
    # ────────────────────────────────────────────────────────────
    def _on_disconnect(self):
        """Called whenever the connection ends or fails."""
        import time
        if self._disconnect_started_at is None:
            self._disconnect_started_at = time.time()
        if self._disconnect_grace_task and not self._disconnect_grace_task.done():
            return  # grace timer already running
        self._disconnect_grace_task = asyncio.create_task(
            self._grace_then_mark_offline()
        )

    async def _grace_then_mark_offline(self):
        """Wait grace seconds; if still disconnected, mark all ONUs offline."""
        try:
            await asyncio.sleep(OFFLINE_GRACE_SECONDS)
        except asyncio.CancelledError:
            return
        if self.connected:
            return  # reconnected already
        try:
            print(f"[ALARM:{self.olt_name}] Offline >{OFFLINE_GRACE_SECONDS}s → marking ONUs offline")
            mark_all_olt_onus_offline(
                self.olt_name, self.olt_ip,
                cause="olt_unreachable",
                detail=f"alarm listener disconnected >{OFFLINE_GRACE_SECONDS}s",
            )
            self._marked_offline = True
        except Exception as e:
            print(f"[ALARM:{self.olt_name}] Failed to mark ONUs offline: {e}")

    def _on_successful_connect(self):
        """Cancel grace timer; schedule a refresh scan if we were offline long enough."""
        import time
        was_marked = self._marked_offline
        downtime = 0.0
        if self._disconnect_started_at is not None:
            downtime = time.time() - self._disconnect_started_at

        if self._disconnect_grace_task and not self._disconnect_grace_task.done():
            self._disconnect_grace_task.cancel()
        self._disconnect_grace_task = None
        self._disconnect_started_at = None

        if was_marked:
            self._marked_offline = False
            if downtime >= 15.0:
                print(f"[ALARM:{self.olt_name}] Reconnected after {downtime:.0f}s — scheduling refresh scan")
                try:
                    asyncio.create_task(self._trigger_refresh_scan())
                except Exception as e:
                    print(f"[ALARM:{self.olt_name}] Could not schedule refresh scan: {e}")

    async def _trigger_refresh_scan(self):
        """Fire a monitor scan for this OLT so Status updates quickly."""
        try:
            await run_monitor_async(self.olt_name)
            print(f"[ALARM:{self.olt_name}] Refresh scan complete")
        except Exception as e:
            print(f"[ALARM:{self.olt_name}] Refresh scan failed: {e}")

    async def _run(self):
        self.started_at = _now_str()
        attempt = 0
        while not self._stop.is_set():
            try:
                await self._connect_and_listen()
                attempt = 0
            except asyncio.CancelledError:
                return
            except Exception as e:
                self.connected = False
                self.last_error = str(e)
                print(f"[ALARM:{self.olt_name}] Disconnect: {e}")
            if self._stop.is_set():
                return
            delay = ALARM_BACKOFF[min(attempt, len(ALARM_BACKOFF) - 1)]
            attempt += 1
            self.reconnects += 1
            print(f"[ALARM:{self.olt_name}] Reconnect in {delay}s (attempt {attempt})")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=delay)
            except asyncio.TimeoutError:
                pass

    async def _connect_and_listen(self):
        h, p = _split_host_port(self.olt_ip, 23)
        print(f"[ALARM:{self.olt_name}] Connecting to {h}:{p}")

        writer = None
        try:
            reader, writer = await asyncio.open_connection(h, p)
            self.connected = True
            try:
                await telnet_login(reader, writer, CDATA_USERNAME, CDATA_PASSWORD)
                print(f"[ALARM:{self.olt_name}] Logged in, streaming alarms")
                self._on_successful_connect()
                buf = ""
                while not self._stop.is_set():
                    try:
                        chunk = await asyncio.wait_for(reader.read(4096), timeout=60)
                    except asyncio.TimeoutError:
                        continue
                    if not chunk:
                        raise ConnectionError("OLT closed the connection")
                    text = chunk.decode("utf-8", errors="ignore")
                    buf += text
                    while "\n" in buf:
                        line, buf = buf.split("\n", 1)
                        line = line.strip()
                        if line:
                            await self._handle_line(line)
            finally:
                self.connected = False
                if writer is not None:
                    try:
                        writer.close()
                        await writer.wait_closed()
                    except Exception:
                        pass
        finally:
            # Fires regardless of failure mode (connect refused, timeout,
            # login failure, mid-stream reset). Triggers the Scenario D
            # grace timer → mark_all_olt_onus_offline().
            self._on_disconnect()

    async def _handle_line(self, line: str):
        m = _ALARM_RE.search(line)
        if not m:
            return
        _slot, port, onu_id, state = m.groups()
        state = state.lower()
        port_i = int(port)
        onu_id_str = str(int(onu_id))

        mac_hint = None
        mm = _ALARM_MAC_RE.search(line)
        if mm:
            mac_hint = mm.group(1).lower().replace("-", ":")

        self.events_processed += 1
        self.last_event_at = _now_str()

        append_alarm_log(self.olt_name, self.olt_ip, port_i, onu_id_str, state, mac_hint, line)

        async with _file_write_lock:
            await self._apply_state_change(port_i, onu_id_str, state, mac_hint, line)

    async def _apply_state_change(self, port: int, onu_id: str,
                                   state: str, mac_hint: Optional[str],
                                   raw_line: str = ""):
        data = load_previous_results()
        olt_ip = self.olt_ip
        if olt_ip not in data:
            data[olt_ip] = {}
        port_str = str(port)
        if port_str not in data[olt_ip]:
            data[olt_ip][port_str] = []

        now = _now_str()
        found = None
        for onu in data[olt_ip][port_str]:
            if str(onu.get("ID", onu.get("onu_id", ""))) == onu_id:
                found = onu
                break

        if found is None:
            found = {
                "ID":           onu_id,
                "Name":         "",
                "Mac address":  mac_hint or "",
                "Status":       state,
                "Onu signal":   "N/A",
                "Learned MACs": [],
                "first_seen":   now,
                "last_seen":    now,
                "last_alarm":   state,
                "last_alarm_at": now,
            }
            # If we first learn about this ONU via an offline alarm,
            # capture the cause immediately.
            if state == "offline":
                found["cause"] = classify_alarm_cause(raw_line)
                found["cause_detail"] = (raw_line or "").strip()
                found["cause_at"] = now
            data[olt_ip][port_str].append(found)
        else:
            prev_state = found.get("Status")
            found["Status"] = state
            found["last_alarm"] = state
            found["last_alarm_at"] = now
            if state == "online":
                found["last_seen"] = now
            if mac_hint and not found.get("Mac address"):
                found["Mac address"] = mac_hint
            found.setdefault("Name", "")
            found.setdefault("Learned MACs", [])
            found.setdefault("Onu signal", "N/A")
            if prev_state != state:
                print(f"[ALARM:{self.olt_name}] ONU {port}/{onu_id}: {prev_state} -> {state}")
                if state == "offline":
                    found["cause"] = classify_alarm_cause(raw_line)
                    found["cause_detail"] = (raw_line or "").strip()
                    found["cause_at"] = now
                elif state == "online":
                    found.pop("cause", None)
                    found.pop("cause_detail", None)
                    found.pop("cause_at", None)

        save_results(data)

        if olt_ip in _results_cache:
            cache_ports = _results_cache[olt_ip]
            cache_ports.setdefault(port_str, [])
            cache_found = None
            for onu in cache_ports[port_str]:
                if str(onu.get("ID", onu.get("onu_id", ""))) == onu_id:
                    cache_found = onu
                    break
            if cache_found is None:
                cache_ports[port_str].append(dict(found))
            else:
                cache_found.update({
                    "Status":        state,
                    "last_alarm":    state,
                    "last_alarm_at": now,
                })
                if state == "online":
                    cache_found["last_seen"] = now
                    cache_found.pop("cause", None)
                    cache_found.pop("cause_detail", None)
                    cache_found.pop("cause_at", None)
                elif state == "offline":
                    cache_found["cause"] = classify_alarm_cause(raw_line)
                    cache_found["cause_detail"] = (raw_line or "").strip()
                    cache_found["cause_at"] = now


_alarm_listeners: Dict[str, AlarmListener] = {}


async def _start_all_alarm_listeners():
    if not ALARMS_ENABLED:
        print("[ALARM] Disabled in config — no listeners started")
        return
    ensure_alarm_log_file()
    for name, info in CDATA_OLT_DEVICES.items():
        listener = AlarmListener(name, info["ip"])
        _alarm_listeners[name] = listener
        listener.start()
        print(f"[ALARM] Started listener for {name} ({info['ip']})")


async def _stop_all_alarm_listeners():
    for listener in _alarm_listeners.values():
        await listener.stop()
    _alarm_listeners.clear()


# ============================================================
# NAME RETRY LOOP (background, every N seconds)
# ============================================================
def _name_retry_once() -> Dict:
    """
    Scan onu_status.json; for each ONU with empty/missing name,
    try to resolve from mac_address.txt via Learned MACs.
    Write to onu_names.json (source='auto') and log to name_updates.txt.
    Only fills EMPTY names (never re-evaluates existing ones).
    """
    stats = {"scanned": 0, "resolved": 0, "skipped_named": 0, "no_match": 0}

    # Fresh PPP map (file read only — no OLT contact)
    global _ppp_map, _ppp_loaded_at
    _ppp_map = load_ppp_sessions()
    _ppp_loaded_at = _now_str()

    data = load_previous_results()
    names = load_onu_names()
    dirty_names = False

    for olt_ip, ports in data.items():
        olt_name = _olt_name_by_ip(olt_ip) or olt_ip
        for port_str, onus in ports.items():
            for onu in onus:
                stats["scanned"] += 1
                onu_mac_pretty = _pretty_mac(onu.get("Mac address", ""))
                if not onu_mac_pretty:
                    continue

                # If a name already exists in onu_names.json, skip (rule B)
                existing_entry = names.get(onu_mac_pretty)
                if existing_entry and existing_entry.get("name"):
                    stats["skipped_named"] += 1
                    continue

                learned = onu.get("Learned MACs", []) or []
                resolved = resolve_name_from_learned(learned)
                if not resolved:
                    stats["no_match"] += 1
                    continue

                resolved_name, via_mac = resolved

                names[onu_mac_pretty] = {
                    "name": resolved_name,
                    "source": "auto",
                    "updated_at": _now_str(),
                }
                dirty_names = True
                stats["resolved"] += 1

                append_name_update(
                    olt_name, olt_ip,
                    int(port_str) if port_str.isdigit() else None,
                    str(onu.get("ID", onu.get("onu_id", ""))),
                    onu_mac_pretty, resolved_name, via_mac, "auto",
                )

    if dirty_names:
        _save_names(names)

    return stats


async def _name_retry_loop():
    print(f"[NAME-RETRY] Started (interval={_name_retry_state['interval']}s)")
    ensure_name_updates_file()
    while True:
        try:
            interval = max(10, int(_name_retry_state["interval"]))
            next_dt = datetime.now() + timedelta(seconds=interval)
            _name_retry_state["next_run"] = next_dt.strftime("%Y-%m-%d %H:%M:%S")

            # Sleep in small chunks so toggling is responsive
            slept = 0
            while slept < interval:
                chunk = min(2, interval - slept)
                await asyncio.sleep(chunk)
                slept += chunk

            _name_retry_state["running"] = True
            stats = _name_retry_once()
            _name_retry_state["running"] = False
            _name_retry_state["last_run"] = _now_str()
            _name_retry_state["last_scanned"] = stats["scanned"]
            _name_retry_state["last_resolved"] = stats["resolved"]
            _name_retry_state["total_resolved"] += stats["resolved"]

            if stats["resolved"] > 0:
                print(f"[NAME-RETRY] resolved={stats['resolved']} "
                      f"scanned={stats['scanned']} skipped_named={stats['skipped_named']}")
        except asyncio.CancelledError:
            print("[NAME-RETRY] Cancelled")
            return
        except Exception as e:
            _name_retry_state["running"] = False
            print(f"[NAME-RETRY] Loop error: {e}")
            await asyncio.sleep(5)


# ============================================================
# HIGH-LEVEL OPERATIONS
# ============================================================
async def run_monitor_async(olt_name: str, ports: Optional[List[int]] = None) -> Dict[str, List[Dict]]:
    if olt_name not in CDATA_OLT_DEVICES:
        raise ValueError(f"Unknown OLT: {olt_name}")
    olt_ip = CDATA_OLT_DEVICES[olt_name]["ip"]
    scan_ports = ports or CDATA_PORTS
    lock = await get_olt_lock(olt_name)
    async with lock:
        n = refresh_ppp_sessions()
        print(f"[PPP] Loaded {n} session(s) from {MAC_ADDRESS_FILE}")
        try:
            current_all = await monitor_olt(olt_ip, scan_ports)
        except OltUnreachableError as e:
            print(f"[CDATA] OLT unreachable ({olt_name} / {olt_ip}): {e.reason}")
            n = mark_all_olt_onus_offline(
                olt_name, olt_ip,
                cause="olt_unreachable",
                detail=str(e.reason),
            )
            print(f"[CDATA] Marked {n} ONU(s) offline for {olt_name}")
            if olt_ip in _results_cache:
                return _results_cache[olt_ip]
            return load_previous_results().get(olt_ip, {})
        async with _file_write_lock:
            prev_data = load_previous_results()
            merged = upsert_olt_scan(olt_name, olt_ip, current_all, prev_data)
            enriched = enrich_with_names(merged)
            _results_cache[olt_ip] = enriched
            save_results(prev_data)
            return enriched


def get_cached_results(olt_name: str) -> Dict[str, List[Dict]]:
    if olt_name not in CDATA_OLT_DEVICES:
        raise ValueError(f"Unknown OLT: {olt_name}")
    olt_ip = CDATA_OLT_DEVICES[olt_name]["ip"]
    if olt_ip in _results_cache:
        return _results_cache[olt_ip]
    data = load_previous_results()
    return data.get(olt_ip, {})


def search_all(query: str, status_filter: Optional[str] = None,
               limit: int = 50) -> List[Dict]:
    data = load_previous_results()
    if not data:
        return []
    q = query.lower().strip()
    q_mac  = re.sub(r"[:\-\s]", "", q)
    q_name = re.sub(r"[_\s]+", "", q)
    names = load_onu_names()
    results: List[Dict] = []
    for olt_ip, ports in data.items():
        olt_name = _olt_name_by_ip(olt_ip) or olt_ip
        for port_str, onu_list in ports.items():
            for onu in onu_list:
                if status_filter and onu.get("Status") != status_filter:
                    continue
                onu_mac = onu.get("Mac address", "")
                mac_clean = re.sub(r"[:\-\s]", "", onu_mac.lower()) if onu_mac else ""
                entry = names.get(_pretty_mac(onu_mac))
                resolved_name = (entry or {}).get("name", "") or ""
                name_norm = re.sub(r"[_\s]+", "", resolved_name.lower())
                hit = (q_name and name_norm and q_name in name_norm) or \
                      (q_mac and mac_clean and q_mac in mac_clean)
                if hit:
                    results.append({
                        "olt":     olt_name,
                        "olt_ip":  olt_ip,
                        "port":    port_str,
                        "onu":     enrich_single_onu(onu),
                    })
                    if len(results) >= limit:
                        return results
    return results


def rename_onu(olt_name: str, onu_mac: str, new_name: str) -> bool:
    if olt_name not in CDATA_OLT_DEVICES:
        raise ValueError(f"Unknown OLT: {olt_name}")
    return upsert_name(onu_mac, new_name, source="manual")


def rename_onu_by_id(olt_name: str, port: int, onu_id: str, new_name: str) -> bool:
    if olt_name not in CDATA_OLT_DEVICES:
        raise ValueError(f"Unknown OLT: {olt_name}")
    olt_ip = CDATA_OLT_DEVICES[olt_name]["ip"]
    port_str = str(port)
    data = load_previous_results()
    onus = data.get(olt_ip, {}).get(port_str, [])
    for onu in onus:
        if str(onu.get("ID", onu.get("onu_id", ""))) == str(onu_id):
            return upsert_name(onu.get("Mac address", ""), new_name, source="manual")
    raise ValueError(f"ONU not found: olt={olt_name} port={port} onu_id={onu_id}")


def delete_offline_onu(olt_name: str, port: int, onu_id: str, mac: str) -> bool:
    if olt_name not in CDATA_OLT_DEVICES:
        raise ValueError(f"Unknown OLT: {olt_name}")
    olt_ip = CDATA_OLT_DEVICES[olt_name]["ip"]
    port_str = str(port)
    mac_norm = _norm_mac(mac)

    def _matches(o: Dict) -> bool:
        same_id = str(o.get("ID", o.get("onu_id", ""))) == str(onu_id)
        is_offline = o.get("Status") in ("offline", "🔴")
        same_mac = _norm_mac(o.get("Mac address", o.get("mac", ""))) == mac_norm
        return same_id and is_offline and same_mac

    data = load_previous_results()
    if olt_ip in data and port_str in data[olt_ip]:
        data[olt_ip][port_str] = [o for o in data[olt_ip][port_str] if not _matches(o)]
        save_results(data)
    if olt_ip in _results_cache and port_str in _results_cache[olt_ip]:
        _results_cache[olt_ip][port_str] = [
            o for o in _results_cache[olt_ip][port_str] if not _matches(o)
        ]
    return True


async def reboot_onu_async(olt_name: str, port: int, onu_id: str) -> Tuple[bool, str]:
    if olt_name not in CDATA_OLT_DEVICES:
        raise ValueError(f"Unknown OLT: {olt_name}")
    olt_ip = CDATA_OLT_DEVICES[olt_name]["ip"]
    return await reboot_onu(olt_ip, port, onu_id)


def is_olt_reachable(host: str, port: int = 23, timeout: float = 3.0) -> bool:
    try:
        h, p = _split_host_port(host, port)
        with socket.create_connection((h, p), timeout=timeout):
            return True
    except Exception:
        return False


def _olt_name_by_ip(ip: str) -> Optional[str]:
    for name, info in CDATA_OLT_DEVICES.items():
        if info["ip"] == ip:
            return name
    return None


# ============================================================
# DASHBOARD AGGREGATION (now with lists)
# ============================================================
def _signal_band(signal_str: str) -> Optional[str]:
    if not signal_str or signal_str == "N/A":
        return None
    try:
        m = re.search(r"(-?\d+(?:\.\d+)?)", signal_str)
        if not m:
            return None
        val = float(m.group(1))
    except Exception:
        return None
    if val <= SIGNAL_CRITICAL_DBM:
        return "critical"
    if val <= SIGNAL_WARNING_DBM:
        return "warning"
    return None


def _make_bucket_item(olt_name: str, olt_ip: str, port_str: str, onu: Dict,
                      enriched: Dict) -> Dict:
    """Compact object for dashboard bucket lists."""
    return {
        "olt":         olt_name,
        "olt_ip":      olt_ip,
        "port":        port_str,
        "ID":          onu.get("ID", onu.get("onu_id", "")),
        "Name":        enriched.get("Name", "") or onu.get("Name", "") or "",
        "Mac address": onu.get("Mac address", ""),
        "Onu signal":  onu.get("Onu signal", "N/A"),
        "Learned MACs": onu.get("Learned MACs", []) or [],
        "Status":      onu.get("Status", ""),
        "signal_band": _signal_band(onu.get("Onu signal", "")),
        "first_seen":  onu.get("first_seen"),
        "last_seen":   onu.get("last_seen"),
    }


def build_dashboard() -> Dict:
    data = load_previous_results()
    names = load_onu_names()

    totals = {
        "online": 0,
        "offline": 0,
        "total": 0,
        "new_24h": 0,
        "olts_count": len(CDATA_OLT_DEVICES),
    }
    signals = {
        "warning": 0,
        "critical": 0,
        "warning_threshold": SIGNAL_WARNING_DBM,
        "critical_threshold": SIGNAL_CRITICAL_DBM,
    }
    per_olt: List[Dict] = []
    pon_outages: List[Dict] = []

    lists = {
        "online":    [],
        "offline":   [],
        "warning":   [],
        "critical":  [],
        "new_24h":   [],
    }

    now_dt = datetime.now()
    cutoff_24h = now_dt - timedelta(hours=24)

    for olt_name, info in CDATA_OLT_DEVICES.items():
        olt_ip = info["ip"]
        ports = data.get(olt_ip, {})
        olt_online = 0
        olt_offline = 0

        for port_str, onus in ports.items():
            port_online = 0
            port_offline = 0

            for onu in onus:
                enriched = enrich_single_onu(onu)
                item = _make_bucket_item(olt_name, olt_ip, port_str, onu, enriched)

                status = onu.get("Status")
                band = _signal_band(onu.get("Onu signal", ""))

                if status == "online":
                    totals["online"] += 1
                    olt_online += 1
                    port_online += 1
                    if len(lists["online"]) < DASH_LIST_LIMIT:
                        lists["online"].append(item)
                    if band == "warning":
                        signals["warning"] += 1
                        if len(lists["warning"]) < DASH_LIST_LIMIT:
                            lists["warning"].append(item)
                    elif band == "critical":
                        signals["critical"] += 1
                        if len(lists["critical"]) < DASH_LIST_LIMIT:
                            lists["critical"].append(item)
                else:
                    totals["offline"] += 1
                    olt_offline += 1
                    port_offline += 1
                    if len(lists["offline"]) < DASH_LIST_LIMIT:
                        lists["offline"].append(item)

                fs = onu.get("first_seen")
                if fs:
                    try:
                        fs_dt = datetime.strptime(fs, "%Y-%m-%d %H:%M:%S")
                        if fs_dt >= cutoff_24h:
                            totals["new_24h"] += 1
                            if len(lists["new_24h"]) < DASH_LIST_LIMIT:
                                lists["new_24h"].append(item)
                    except Exception:
                        pass

            total_ever = port_online + port_offline
            if total_ever >= PON_OUTAGE_MIN_ONUS:
                if port_online == 0:
                    severity = "critical"
                elif (port_offline / total_ever) > PON_OUTAGE_PARTIAL:
                    severity = "warning"
                else:
                    continue
                last_seen = max(
                    (o.get("last_seen") or "" for o in onus),
                    default="",
                )
                pon_outages.append({
                    "olt": olt_name,
                    "olt_ip": olt_ip,
                    "port": port_str,
                    "online": port_online,
                    "offline": port_offline,
                    "total_ever": total_ever,
                    "severity": severity,
                    "last_online_seen": last_seen or None,
                })

        per_olt.append({
            "olt": olt_name,
            "olt_ip": olt_ip,
            "online": olt_online,
            "offline": olt_offline,
            "total": olt_online + olt_offline,
        })

    totals["total"] = totals["online"] + totals["offline"]
    pon_outages.sort(key=lambda x: (0 if x["severity"] == "critical" else 1, -x["total_ever"]))

    return {
        "time": _now_str(),
        "totals": totals,
        "signals": signals,
        "lists": lists,
        "pon_outages": pon_outages,
        "per_olt": per_olt,
        "list_limit": DASH_LIST_LIMIT,
    }


# ============================================================
# AUTO-SCAN SCHEDULER
# ============================================================
async def _auto_scan_cycle_once() -> Dict[str, Dict]:
    if _auto_scan_state["running"]:
        return {"_skipped": {"reason": "previous cycle still running"}}
    _auto_scan_state["running"] = True
    result: Dict[str, Dict] = {}
    try:
        for olt_name in list(CDATA_OLT_DEVICES.keys()):
            try:
                merged = await run_monitor_async(olt_name)
                total = sum(len(v) for v in merged.values())
                result[olt_name] = {"ok": True, "total_onus": total, "error": None}
                print(f"[AUTO-SCAN] {olt_name}: {total} ONUs")
            except Exception as e:
                result[olt_name] = {"ok": False, "total_onus": 0, "error": str(e)}
                print(f"[AUTO-SCAN] {olt_name}: FAILED - {e}")
    finally:
        _auto_scan_state["running"] = False
    return result


async def _auto_scan_loop():
    print(f"[AUTO-SCAN] Scheduler started (interval={_auto_scan_state['interval']}s)")
    while True:
        try:
            if not _auto_scan_state["enabled"]:
                _auto_scan_state["next_run"] = None
                await asyncio.sleep(2)
                continue
            interval = max(10, int(_auto_scan_state["interval"]))
            next_dt = datetime.now() + timedelta(seconds=interval)
            _auto_scan_state["next_run"] = next_dt.strftime("%Y-%m-%d %H:%M:%S")
            slept = 0
            while slept < interval:
                if not _auto_scan_state["enabled"]:
                    break
                chunk = min(2, interval - slept)
                await asyncio.sleep(chunk)
                slept += chunk
            if not _auto_scan_state["enabled"]:
                continue
            print("[AUTO-SCAN] Cycle start")
            _auto_scan_state["last_result"] = await _auto_scan_cycle_once()
            _auto_scan_state["last_run"] = _now_str()
            print("[AUTO-SCAN] Cycle done")
        except asyncio.CancelledError:
            print("[AUTO-SCAN] Cancelled")
            return
        except Exception as e:
            print(f"[AUTO-SCAN] Loop error: {e}")
            await asyncio.sleep(5)


# ============================================================
# FASTAPI APP
# ============================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _auto_scan_task, _name_retry_task
    ensure_onu_status_file()
    ensure_new_onus_file()
    ensure_alarm_log_file()
    ensure_name_updates_file()

    n = refresh_ppp_sessions()
    print(f"[PPP] Startup: loaded {n} session(s) from {MAC_ADDRESS_FILE}")

    _auto_scan_task = asyncio.create_task(_auto_scan_loop())
    _name_retry_task = asyncio.create_task(_name_retry_loop())
    await _start_all_alarm_listeners()

    try:
        yield
    finally:
        if _auto_scan_task:
            _auto_scan_task.cancel()
            try:
                await _auto_scan_task
            except asyncio.CancelledError:
                pass
        if _name_retry_task:
            _name_retry_task.cancel()
            try:
                await _name_retry_task
            except asyncio.CancelledError:
                pass
        await _stop_all_alarm_listeners()


app = FastAPI(
    title="DumbOLT for Cdata",
    description=(
        "EPON monitor & ONU management API. "
        "Persistent alarm listeners, auto-naming with 60s retry, dashboard aggregation."
    ),
    version="2.5.0",
    lifespan=lifespan,
)

if CORS_ORIGINS:
    print(f"[CORS] Enabled for origins: {CORS_ORIGINS}")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    print("[CORS] Disabled (no origins configured)")


# ---------- Pydantic models ----------
class MonitorRequest(BaseModel):
    ports: Optional[List[int]] = None

class RebootRequest(BaseModel):
    olt: str
    port: int
    onu_id: str

class RenameRequest(BaseModel):
    olt: str
    port: int
    onu_id: str
    name: str

class RenameByMacRequest(BaseModel):
    olt: str
    onu_mac: str
    name: str

class DeleteOnuRequest(BaseModel):
    olt: str
    port: int
    onu_id: str
    mac: str

class AutoScanToggleRequest(BaseModel):
    enabled: bool

class AutoScanConfigRequest(BaseModel):
    enabled: Optional[bool] = None
    interval_seconds: Optional[int] = Field(default=None, ge=10, le=86400)


# ---------- Helpers ----------
def _require_olt(olt: str) -> Dict[str, str]:
    if olt not in CDATA_OLT_DEVICES:
        raise HTTPException(status_code=404, detail=f"Unknown OLT: {olt}")
    return CDATA_OLT_DEVICES[olt]


# ---------- Health / metadata ----------
@app.get("/health", tags=["meta"])
def health():
    listeners = {
        name: {
            "connected":         l.connected,
            "started_at":        l.started_at,
            "last_event_at":     l.last_event_at,
            "last_error":        l.last_error,
            "events_processed":  l.events_processed,
            "reconnects":        l.reconnects,
        }
        for name, l in _alarm_listeners.items()
    }
    return {
        "status": "ok",
        "time": _now_str(),
        "olts_loaded": len(CDATA_OLT_DEVICES),
        "names_entries": len(load_onu_names()),
        "ppp_sessions": len(_ppp_map),
        "ppp_loaded_at": _ppp_loaded_at,
        "alarms_enabled": ALARMS_ENABLED,
        "alarm_listeners": listeners,
        "auto_scan": {
            "enabled":  _auto_scan_state["enabled"],
            "interval": _auto_scan_state["interval"],
            "running":  _auto_scan_state["running"],
            "last_run": _auto_scan_state["last_run"],
            "next_run": _auto_scan_state["next_run"],
        },
        "name_retry": dict(_name_retry_state),
    }


@app.get("/config", tags=["meta"])
def get_config():
    return {
        "bts_config":     BTS_CONFIG_PATH,
        "cdata_config":   CDATA_CONFIG_PATH,
        "save_file":      SAVE_FILE,
        "names_file":     NAMES_FILE,
        "ppp_file":       MAC_ADDRESS_FILE,
        "alarm_log":      ALARM_LOG_FILE,
        "name_updates":   NAME_UPDATES_FILE,
        "discovery_log":  NEW_ONUS_FILE,
        "default_ports":  CDATA_PORTS,
        "api_port":       API_PORT,
        "cors_origins":   CORS_ORIGINS,
        "olts":           list(CDATA_OLT_DEVICES.keys()),
        "alarms_enabled": ALARMS_ENABLED,
        "dashboard": {
            "refresh_interval_seconds": DASH_REFRESH_INTERVAL,
            "signal_warning_dbm":       SIGNAL_WARNING_DBM,
            "signal_critical_dbm":      SIGNAL_CRITICAL_DBM,
            "pon_outage_partial_ratio": PON_OUTAGE_PARTIAL,
            "pon_outage_min_onus_ever": PON_OUTAGE_MIN_ONUS,
            "list_limit":               DASH_LIST_LIMIT,
        },
        "names": {
            "retry_interval_seconds": NAME_RETRY_INTERVAL,
            "updates_log":            NAME_UPDATES_FILE,
        },
    }


# ---------- OLTs ----------
@app.get("/olts", tags=["olts"])
def list_olts():
    out = []
    for name, info in CDATA_OLT_DEVICES.items():
        out.append({
            "name":      name,
            "ip":        info["ip"],
            "reachable": is_olt_reachable(info["ip"]),
        })
    return {"count": len(out), "olts": out}


@app.get("/olts/{olt}/reachable", tags=["olts"])
def olt_reachable(olt: str):
    info = _require_olt(olt)
    return {"olt": olt, "ip": info["ip"], "reachable": is_olt_reachable(info["ip"])}


@app.get("/olts/{olt}/results", tags=["olts"])
def olt_results(olt: str):
    _require_olt(olt)
    data = get_cached_results(olt)
    enriched = enrich_with_names(data)
    total = sum(len(v) for v in enriched.values())
    return {"olt": olt, "ports": enriched, "total_onus": total}


@app.get("/olts/{olt}/ports/{port}", tags=["olts"])
def olt_port_results(olt: str, port: int):
    _require_olt(olt)
    data = get_cached_results(olt)
    port_str = str(port)
    if port_str not in data:
        raise HTTPException(status_code=404, detail=f"No data for port {port}")
    enriched = enrich_with_names({port_str: data[port_str]})
    return {"olt": olt, "port": port, "onus": enriched[port_str]}


# ---------- Monitor ----------
@app.post("/olts/{olt}/monitor", tags=["monitor"])
async def monitor(olt: str, req: MonitorRequest = MonitorRequest()):
    _require_olt(olt)
    try:
        final = await run_monitor_async(olt, req.ports)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Monitor failed: {e}")
    total = sum(len(v) for v in final.values())
    return {
        "olt": olt,
        "ports_scanned": list(final.keys()),
        "total_onus": total,
        "ports": final,
    }


# ---------- Search ----------
@app.get("/search", tags=["search"])
def search(
    q: str = Query(..., min_length=1),
    status: Optional[str] = Query(None, pattern="^(online|offline)$"),
    limit: int = Query(50, ge=1, le=500),
):
    hits = search_all(q, status_filter=status, limit=limit)
    return {"query": q, "status_filter": status, "count": len(hits), "results": hits}


# ---------- Actions ----------
@app.post("/reboot", tags=["actions"])
async def reboot(req: RebootRequest):
    _require_olt(req.olt)
    try:
        success, log = await reboot_onu_async(req.olt, req.port, req.onu_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Reboot error: {e}")
    if not success:
        raise HTTPException(status_code=502, detail={"message": "Reboot failed", "log": log})
    return {"success": True, "log": log}


@app.post("/rename", tags=["actions"])
def rename(req: RenameRequest):
    _require_olt(req.olt)
    try:
        rename_onu_by_id(req.olt, req.port, req.onu_id, req.name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {
        "success": True,
        "olt": req.olt, "port": req.port, "onu_id": req.onu_id,
        "name": req.name, "source": "manual",
        "written_to": NAMES_FILE,
    }


@app.post("/rename-by-mac", tags=["actions"])
def rename_by_mac(req: RenameByMacRequest):
    _require_olt(req.olt)
    ok = rename_onu(req.olt, req.onu_mac, req.name)
    if not ok:
        raise HTTPException(status_code=500, detail="Could not write names file")
    return {
        "success": True,
        "olt": req.olt, "onu_mac": req.onu_mac, "name": req.name,
        "source": "manual", "written_to": NAMES_FILE,
    }


@app.delete("/onu", tags=["actions"])
def delete_onu(req: DeleteOnuRequest):
    _require_olt(req.olt)
    delete_offline_onu(req.olt, req.port, req.onu_id, req.mac)
    return {"success": True}


# ---------- Names ----------
@app.get("/names", tags=["names"])
def get_names():
    names = load_onu_names()
    return {"count": len(names), "names": names}


@app.get("/names/lookup", tags=["names"])
def names_lookup(mac: str = Query(..., min_length=6)):
    names = load_onu_names()
    key = _pretty_mac(mac)
    if key not in names:
        raise HTTPException(status_code=404, detail="No name for that MAC")
    return {"mac": key, **names[key]}


@app.get("/names/retry-status", tags=["names"])
def names_retry_status():
    return dict(_name_retry_state)


@app.post("/names/retry-now", tags=["names"])
def names_retry_now():
    _name_retry_state["running"] = True
    try:
        stats = _name_retry_once()
    finally:
        _name_retry_state["running"] = False
    _name_retry_state["last_run"] = _now_str()
    _name_retry_state["last_scanned"] = stats["scanned"]
    _name_retry_state["last_resolved"] = stats["resolved"]
    _name_retry_state["total_resolved"] += stats["resolved"]
    return {"success": True, **stats}


@app.get("/names/updates", tags=["names"])
def names_updates(limit: int = Query(100, ge=1, le=5000)):
    if not os.path.exists(NAME_UPDATES_FILE):
        return {"file": NAME_UPDATES_FILE, "count": 0, "lines": []}
    try:
        with open(NAME_UPDATES_FILE, "r", encoding="utf-8") as f:
            lines = [ln.rstrip("\n") for ln in f if ln.strip() and not ln.startswith("#")]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not read name updates: {e}")
    tail = lines[-limit:]
    return {"file": NAME_UPDATES_FILE, "count": len(tail), "lines": tail}


# ---------- PPP ----------
@app.get("/mac-address/count", tags=["ppp"])
def ppp_count():
    return {
        "file": MAC_ADDRESS_FILE,
        "entries": len(_ppp_map),
        "loaded_at": _ppp_loaded_at,
        "raw_lines": _ppp_source_lines,
    }


@app.post("/mac-address/reload", tags=["ppp"])
def ppp_reload():
    n = refresh_ppp_sessions()
    return {"success": True, "entries": n, "loaded_at": _ppp_loaded_at}


@app.get("/mac-address/lookup", tags=["ppp"])
def ppp_lookup(mac: str = Query(..., min_length=6)):
    key = _norm_mac(mac)
    name = _ppp_map.get(key)
    if not name:
        raise HTTPException(status_code=404, detail="No PPP session for that MAC")
    return {"mac": _pretty_mac(mac), "name": name}


# ---------- Alarms ----------
@app.get("/alarms/status", tags=["alarms"])
def alarms_status():
    return {
        "enabled": ALARMS_ENABLED,
        "log_file": ALARM_LOG_FILE,
        "listeners": {
            name: {
                "olt_ip":            l.olt_ip,
                "connected":         l.connected,
                "started_at":        l.started_at,
                "last_event_at":     l.last_event_at,
                "last_error":        l.last_error,
                "events_processed":  l.events_processed,
                "reconnects":        l.reconnects,
            }
            for name, l in _alarm_listeners.items()
        },
    }


@app.get("/alarms/log", tags=["alarms"])
def alarms_log(limit: int = Query(100, ge=1, le=5000)):
    if not os.path.exists(ALARM_LOG_FILE):
        return {"file": ALARM_LOG_FILE, "count": 0, "lines": []}
    try:
        with open(ALARM_LOG_FILE, "r", encoding="utf-8") as f:
            lines = [ln.rstrip("\n") for ln in f if ln.strip() and not ln.startswith("#")]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not read alarm log: {e}")
    tail = lines[-limit:]
    return {"file": ALARM_LOG_FILE, "count": len(tail), "lines": tail}


@app.post("/alarms/{olt}/restart", tags=["alarms"])
async def alarm_restart(olt: str):
    _require_olt(olt)
    listener = _alarm_listeners.get(olt)
    if not listener:
        raise HTTPException(status_code=404, detail=f"No alarm listener for OLT: {olt}")
    await listener.restart()
    return {"success": True, "olt": olt}


# ---------- Dashboard ----------
@app.get("/dashboard", tags=["dashboard"])
def dashboard():
    return build_dashboard()


# ---------- Auto-scan control ----------
@app.get("/auto-scan/status", tags=["auto-scan"])
def auto_scan_status():
    return {
        "enabled":     _auto_scan_state["enabled"],
        "interval":    _auto_scan_state["interval"],
        "running":     _auto_scan_state["running"],
        "last_run":    _auto_scan_state["last_run"],
        "next_run":    _auto_scan_state["next_run"],
        "last_result": _auto_scan_state["last_result"],
    }


@app.post("/auto-scan/toggle", tags=["auto-scan"])
def auto_scan_toggle(req: AutoScanToggleRequest):
    _auto_scan_state["enabled"] = bool(req.enabled)
    return {"enabled": _auto_scan_state["enabled"]}


@app.post("/auto-scan/config", tags=["auto-scan"])
def auto_scan_config(req: AutoScanConfigRequest):
    if req.enabled is not None:
        _auto_scan_state["enabled"] = bool(req.enabled)
    if req.interval_seconds is not None:
        _auto_scan_state["interval"] = int(req.interval_seconds)
    return {"enabled": _auto_scan_state["enabled"], "interval": _auto_scan_state["interval"]}


@app.post("/auto-scan/run-now", tags=["auto-scan"])
async def auto_scan_run_now():
    result = await _auto_scan_cycle_once()
    _auto_scan_state["last_result"] = result
    _auto_scan_state["last_run"] = _now_str()
    return {"success": True, "result": result}


# ---------- Discovery log ----------
@app.get("/discovery-log", tags=["meta"])
def discovery_log(limit: int = Query(100, ge=1, le=1000)):
    if not os.path.exists(NEW_ONUS_FILE):
        return {"file": NEW_ONUS_FILE, "count": 0, "lines": []}
    try:
        with open(NEW_ONUS_FILE, "r", encoding="utf-8") as f:
            lines = [ln.rstrip("\n") for ln in f if ln.strip() and not ln.startswith("#")]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not read log: {e}")
    tail = lines[-limit:]
    return {"file": NEW_ONUS_FILE, "count": len(tail), "lines": tail}


# ============================================================
# ENTRYPOINT
# ============================================================
def _print_startup_banner():
    print("=" * 60)
    print("DumbOLT for Cdata — Stage 2.5")
    print("=" * 60)
    print(f"bts_config.json:   {BTS_CONFIG_PATH}")
    print(f"cdata_config.json: {CDATA_CONFIG_PATH}")
    print(f"onu_status.json:   {SAVE_FILE}")
    print(f"onu_names.json:    {NAMES_FILE}")
    print(f"ppp sessions:      {MAC_ADDRESS_FILE}")
    print(f"alarm log:         {ALARM_LOG_FILE}")
    print(f"name updates:      {NAME_UPDATES_FILE}")
    print(f"discovery log:     {NEW_ONUS_FILE}")
    print(f"API port:          {API_PORT}")
    print(f"CORS origins:      {CORS_ORIGINS or '(disabled)'}")
    print(f"Alarms:            enabled={ALARMS_ENABLED}")
    print(f"Name retry:        every {NAME_RETRY_INTERVAL}s")
    print(f"Auto-scan:         enabled={AUTO_SCAN_ENABLED} interval={AUTO_SCAN_INTERVAL}s")
    print(f"Cdata OLTs loaded: {len(CDATA_OLT_DEVICES)}")
    for name, info in CDATA_OLT_DEVICES.items():
        print(f"  - {name:<25} {info['ip']}")
    print()


if __name__ == "__main__":
    import uvicorn
    _print_startup_banner()
    uvicorn.run(app, host="0.0.0.0", port=API_PORT, log_level="info")
