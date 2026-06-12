## What is DUMBOLT?

**DUMBOLT** is a comprehensive, enterprise-ready monitoring solution specifically designed for CDATA Optical Line Terminals (OLTs). Built with Python and Streamlit, it transforms complex Telnet CLI interactions into a beautiful, intuitive web interface that any network technician can use.

## The Problem We Solve

Network engineers managing FTTH (Fiber to the Home) networks face daily challenges:
- ❌ **No Central Visibility** - Juggling multiple OLTs via SSH/Telnet terminals
- ❌ **Manual Documentation** - Tracking ONU locations in spreadsheets
- ❌ **Delayed Response** - Finding which port a specific customer is on takes minutes
- ❌ **No Historical Data** - No record of when devices go offline or move
- ❌ **Complex Reboots** - Remembering CLI commands for each OLT vendor

## The DUMBOLT Solution

✅ **Single Pane of Glass** - Monitor ALL your OLTs from one dashboard  
✅ **Real-time Status** - Green = Online, Red = Offline, at a glance  
✅ **Instant Search** - Find any customer by MAC address or name in seconds  
✅ **Smart Tracking** - Automatically logs when ONUs move between ports  
✅ **One-Click Actions** - Reboot any ONU with a single button click  
✅ **Historical Logs** - Complete audit trail of all device movements and actions  

## Who Is This For?

- **ISP Network Engineers** - Managing FTTH deployments
- **Data Center Technicians** - Monitoring OLT infrastructure
- **NOC Operators** - 24/7 network operations centers
- **Field Technicians** - Quick remote diagnostics before truck rolls
- **Network Administrators** - Small to medium ISPs

## Key Capabilities

### 📡 Real-Time Monitoring
- Poll any or all ports on any OLT
- Display online/offline status with visual indicators
- Show ONU ID, MAC address, and customer name
- Monitor optical signal strength (RX power)

### 🔍 Advanced Search
- Search by full or partial MAC address
- Search by customer/device name
- Automatic search term highlighting
- Find devices across all OLTs instantly

### 🔄 Device Movement Detection
- Automatically detects when an ONU moves to a different port
- Logs timestamp, old port, and new port
- Prevents duplicate MAC address confusion
- Maintains complete device history

### 🛠️ Remote Management
- Reboot ONUs remotely without CLI access
- Delete offline devices from saved records
- Bulk operations (coming soon)

### 📊 Comprehensive Logging
- Movement logs with timestamps
- Reboot history
- Deletion records
- Export logs to CSV for reporting

## Technical Architecture
