# DumbOLT

**DumbOLT** is a comprehensive, enterprise-ready monitoring solution for
**CDATA Optical Line Terminals (OLTs)**. It turns raw Telnet CLI interactions
into a clean, fast web interface that any network technician can use — from
a NOC operator triaging outages to a field tech confirming a customer's ONU
before a truck roll.

Built as a **two-tier stack**:
- **Python backend (FastAPI)** — talks to the OLTs over Telnet, parses alarms,
  tracks ONU state, exposes a JSON API on port `8310`
- **Laravel frontend (Livewire + Tailwind)** — the web UI, proxies to the API
  server-side, runs on port `9090`

---

## The Problem We Solve

Network engineers managing FTTH (Fiber to the Home) networks face daily challenges:

- ❌ **No Central Visibility** — juggling multiple OLTs via SSH/Telnet terminals
- ❌ **Manual Documentation** — tracking ONU locations in spreadsheets
- ❌ **Delayed Response** — finding which port a specific customer is on takes minutes
- ❌ **No Historical Data** — no record of when devices go offline or why
- ❌ **Complex Reboots** — remembering CLI commands for each OLT vendor
- ❌ **Silent Failures** — power cuts and fiber cuts look identical without alarm analysis

## The DumbOLT Solution

- ✅ **Single Pane of Glass** — monitor all your Cdata OLTs from one dashboard
- ✅ **Real-Time Alarm Stream** — persistent listener per OLT, catches Dying Gasp,
  LOS, and online/offline transitions as they happen
- ✅ **Automatic Offline Classification** — tells you *why* an ONU went offline
  (⚡ power failure, 📡 loss of signal, 🔌 OLT unreachable)
- ✅ **Instant Search** — find any ONU by MAC address or customer name in seconds
- ✅ **One-Click Actions** — reboot or delete an ONU without touching the CLI
- ✅ **Historical Logs** — discovery log, alarm log, name updates — all on disk
- ✅ **Self-Healing** — OLT unreachable? All its ONUs auto-flip to offline until
  it comes back. No stale "online" statuses hiding real outages.
- ✅ **Role-Based Access** — `admin` (full) and `noc` (view + reboot + rename)

## Who Is This For?

- **ISP Network Engineers** managing FTTH deployments
- **Data Center Technicians** monitoring OLT infrastructure
- **NOC Operators** running 24/7 network operations centers
- **Field Technicians** doing quick remote diagnostics before truck rolls
- **Network Administrators** at small to medium ISPs

---


The Python backend is the only process that speaks to the OLT. Laravel never
opens a Telnet session — it just proxies HTTP requests to the FastAPI service.

---

## Key Capabilities

### 📡 Real-Time Monitoring
- Scan any port or all ports on any Cdata OLT
- Online/offline status with visual indicators
- ONU ID, MAC address, customer name, optical signal (RX power)
- Learned MACs per ONU — shows what customer devices sit behind each ONU

### 🔔 Alarm Listener (per OLT)
- Persistent Telnet session per OLT, dedicated to alarms
- Parses `Dying Gasp`, `offline...`, `online...` events
- Classifies causes: `power_loss` / `los` / `olt_unreachable`
- Auto-marks all ONUs offline when the OLT itself goes down (>30s grace)
- Auto-triggers a refresh scan when the OLT comes back

### 🔍 Advanced Search
- Search by full or partial MAC address
- Search by customer name (from `onu_names.json`)
- Filter by status (online / offline)
- Across all OLTs at once, with a configurable result limit

### 🛠️ Remote Management
- Reboot ONUs remotely (no CLI needed)
- Rename ONUs (name is written to `onu_names.json`, keyed by ONU MAC)
- Delete offline ONUs from saved records
- Role-gated: `noc` cannot access auto-scan or listener controls

### 📊 Comprehensive Logging
- `alarm_log.txt` — every alarm event, timestamped
- `new_onus.txt` — append-only discovery log for first-time-seen ONUs
- `name_updates.txt` — every name resolution the retry loop performs
- All plain text, easy to grep or export

### ⏱️ Auto-Scan (opt-in)
- Background scheduler scans every OLT on a configurable interval
- Per-OLT async locks prevent concurrent scans of the same device
- Admin-toggleable at runtime (`/auto-scan/toggle`)
- Run-now button for manual refresh

---

## Data Files

The backend keeps everything in flat files next to the Python script — no DB
required for the monitoring tier.

| File | Purpose | Owner |
|------|---------|-------|
| `bts_config.json` | Full site list (Cdata filter applied to `bts_sites`) | shared (net_data) |
| `cdata_config.json` | OLT credentials, ports, API port, CORS, auto-scan, alarms | backend |
| `onu_status.json` | Operational truth: MAC, learned MACs, signal, timestamps, cause | backend |
| `onu_names.json` | `{onu_mac: name}` map — read by backend, written by name service | external |
| `alarm_log.txt` | Append-only alarm event log | backend |
| `new_onus.txt` | First-sighting log for every new ONU | backend |
| `name_updates.txt` | Log of every name resolution | backend |

The **Laravel UI never touches these files directly** — it goes through the
API.

---

## Configuration

### `bts_config.json` 

Filters down to only Cdata OLTs. A site is included if:
- `olt_type` **contains the substring `cdata`** (case-insensitive), and
- `olt_ip` is present and non-empty

```json
{
  "bts_sites": [
    {
      "name": "Tatooine",
      "olt_ip": "10.10.10.2",
      "olt_type": "Cdata"
    }
  ]
}
