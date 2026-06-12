import asyncio
import time
import re
import json
import os
import pandas as pd
import streamlit as st
import nest_asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from config_loader import load_config, get_olt_devices, get_credentials, get_file_paths, get_settings

# Apply nest_asyncio to handle async in Streamlit
nest_asyncio.apply()

# ------------------- LOAD CONFIGURATION -------------------
try:
    CONFIG = load_config()
    OLT_DEVICES = get_olt_devices(CONFIG)
    USERNAME, PASSWORD = get_credentials(CONFIG)
    FILE_PATHS = get_file_paths(CONFIG)
    SETTINGS = get_settings(CONFIG)
    
    SAVE_FILE = FILE_PATHS.get("save_file", "onu_status.json")
    MAC_ADDRESS_FILE = FILE_PATHS.get("mac_address_file", r"C:\Users\HP\Downloads\mac_address_list.txt")
    LOG_FILE = FILE_PATHS.get("log_file", "onu_movement_log.json")
    SAVE_DEBOUNCE_TIME = SETTINGS.get("save_debounce_time", 2)
    SAVE_BATCH_SIZE = SETTINGS.get("save_batch_size", 5)
    
except Exception as e:
    st.error(f"Failed to load configuration: {e}")
    st.stop()

# ------------------- SESSION STATE INITIALIZATION -------------------
# Initialize session state
if 'monitoring_results' not in st.session_state:
    st.session_state.monitoring_results = {}
if 'reboot_status' not in st.session_state:
    st.session_state.reboot_status = {"active": False, "port": None, "onu_id": None, "message": "", "success": None}
if 'search_query' not in st.session_state:
    st.session_state.search_query = ""
if 'search_results' not in st.session_state:
    st.session_state.search_results = {}
if 'search_port' not in st.session_state:
    st.session_state.search_port = None
if 'search_loading' not in st.session_state:
    st.session_state.search_loading = False
if 'save_queue' not in st.session_state:
    st.session_state.save_queue = []
if 'last_save_time' not in st.session_state:
    st.session_state.last_save_time = 0
if 'save_timer' not in st.session_state:
    st.session_state.save_timer = None
if 'ports_loaded' not in st.session_state:
    st.session_state.ports_loaded = set()
if 'search_olt_ip' not in st.session_state:
    st.session_state.search_olt_ip = None
if 'olt_choice' not in st.session_state:
    st.session_state.olt_choice = "1"
if 'mac_name_map' not in st.session_state:
    st.session_state.mac_name_map = {}
if 'movement_logs' not in st.session_state:
    st.session_state.movement_logs = []
if 'cached_results' not in st.session_state:
    st.session_state.cached_results = {}
if 'cached_mtime' not in st.session_state:
    st.session_state.cached_mtime = 0
if 'delete_confirm' not in st.session_state:
    st.session_state.delete_confirm = {"active": False, "olt_ip": None, "port": None, "onu_id": None, "mac": None}

# ------------------- HELPERS -------------------

def log_to_console(message):
    """Print message to console where Streamlit is running"""
    print(f"[DEBUG] {message}", flush=True)

def load_mac_address_list(file_path):
    """Load MAC addresses and names from the text file"""
    mac_name_map = {}
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Parse the file content
        lines = content.split('\n')
        for line in lines:
            line = line.strip()
            # Match lines like: "1. chike_ezeh                - F4:E4:AD:60:CE:62"
            match = re.search(r'^\s*\d+\.\s+([a-zA-Z_]+)\s*-?\s*([0-9A-F]{2}[:-][0-9A-F]{2}[:-][0-9A-F]{2}[:-][0-9A-F]{2}[:-][0-9A-F]{2}[:-][0-9A-F]{2})', line, re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                mac = match.group(2).strip().lower().replace(":", "").replace("-", "")
                mac_name_map[mac] = name
                log_to_console(f"Loaded MAC: {mac} -> {name}")
                
        log_to_console(f"Loaded {len(mac_name_map)} MAC addresses from file")
        return mac_name_map
        
    except FileNotFoundError:
        log_to_console(f"MAC address list file not found: {file_path}")
        return {}
    except Exception as e:
        log_to_console(f"Error loading MAC address list: {e}")
        return {}

def find_matching_name(mac_address, mac_name_map):
    """Find matching name for MAC address, allowing last character to differ"""
    if not mac_address or not mac_name_map:
        return ""
    
    # Clean the MAC address (remove colons, dashes, and convert to lowercase)
    clean_mac = mac_address.lower().replace(":", "").replace("-", "")
    
    log_to_console(f"Looking for match for: {mac_address} -> {clean_mac}")
    
    # Try exact match first
    if clean_mac in mac_name_map:
        log_to_console(f"Exact match found: {clean_mac} -> {mac_name_map[clean_mac]}")
        return mac_name_map[clean_mac]
    
    # If MAC is exactly 12 characters (full MAC without colons)
    if len(clean_mac) == 12:
        # Try matching first 11 characters (ignore last character)
        partial_mac = clean_mac[:11]
        log_to_console(f"Trying partial match for 12-char MAC: {partial_mac}")
        for stored_mac, name in mac_name_map.items():
            if stored_mac.startswith(partial_mac) and len(stored_mac) == 12:
                log_to_console(f"Partial match found: {stored_mac} -> {name}")
                return name
    
    # If MAC is shorter (like from OLT output might be missing last character)
    elif len(clean_mac) == 11:
        log_to_console(f"Trying partial match for 11-char MAC: {clean_mac}")
        for stored_mac, name in mac_name_map.items():
            if stored_mac.startswith(clean_mac) and len(stored_mac) == 12:
                log_to_console(f"Partial match found: {stored_mac} -> {name}")
                return name
    
    # Also try the reverse - if our MAC has colons but stored doesn't
    mac_without_colons = clean_mac.replace(":", "")
    if mac_without_colons in mac_name_map:
        log_to_console(f"Match after removing colons: {mac_without_colons} -> {mac_name_map[mac_without_colons]}")
        return mac_name_map[mac_without_colons]
    
    # Try partial match without last character for MAC with colons
    if ":" in mac_address and len(mac_address) == 17:
        mac_without_last = mac_address[:-1].lower().replace(":", "")
        log_to_console(f"Trying partial match for MAC with colons: {mac_without_last}")
        for stored_mac, name in mac_name_map.items():
            if stored_mac.startswith(mac_without_last) and len(stored_mac) == 12:
                log_to_console(f"Partial match found: {stored_mac} -> {name}")
                return name
    
    log_to_console(f"No match found for: {mac_address}")
    return ""

def update_existing_results_with_names():
    """Update existing monitoring results with names from MAC address list"""
    if not st.session_state.mac_name_map:
        return
    
    for olt_ip, ports_data in st.session_state.monitoring_results.items():
        for port, onu_list in ports_data.items():
            for onu in onu_list:
                mac = onu.get("Mac address", onu.get("mac", ""))
                if mac and not onu.get("Name"):
                    name = find_matching_name(mac, st.session_state.mac_name_map)
                    if name:
                        onu["Name"] = name

def load_previous_results():
    """Load previous results with error handling and caching"""
    try:
        if os.path.exists(SAVE_FILE):
            # Check file modification time for caching
            file_mtime = os.path.getmtime(SAVE_FILE)
            if ('cached_results' in st.session_state and 
                'cached_mtime' in st.session_state and
                st.session_state.cached_mtime == file_mtime):
                return st.session_state.cached_results
            
            with open(SAVE_FILE, "r") as f:
                results = json.load(f)
                # Cache the results
                st.session_state.cached_results = results
                st.session_state.cached_mtime = file_mtime
                return results
    except (json.JSONDecodeError, IOError) as e:
        log_to_console(f"Error loading previous results: {e}")
        # Create backup of corrupted file
        if os.path.exists(SAVE_FILE):
            backup_name = f"{SAVE_FILE}.backup.{int(time.time())}"
            os.rename(SAVE_FILE, backup_name)
            log_to_console(f"Created backup of corrupted file: {backup_name}")
    return {}

def save_results_async(results):
    """Save results asynchronously to avoid blocking the main thread, preserving all existing data"""
    def save_task():
        try:
            # Load existing data first
            existing_data = {}
            if os.path.exists(SAVE_FILE):
                try:
                    with open(SAVE_FILE, "r") as f:
                        existing_data = json.load(f)
                except (json.JSONDecodeError, IOError):
                    # If file is corrupted, keep existing_data as empty dict
                    pass
            
            # Merge new results with existing data (new results take precedence for overlapping keys)
            for olt_ip, olt_data in results.items():
                if olt_ip not in existing_data:
                    existing_data[olt_ip] = {}
                
                for port, port_data in olt_data.items():
                    # Only update if we have new data for this port
                    if port_data:
                        existing_data[olt_ip][port] = port_data
            
            # Update cache
            st.session_state.cached_results = existing_data
            st.session_state.cached_mtime = time.time()
            
            # Use atomic write to prevent corruption
            temp_file = f"{SAVE_FILE}.tmp"
            with open(temp_file, "w") as f:
                json.dump(existing_data, f, indent=2)
            
            # Atomic replace
            if os.path.exists(SAVE_FILE):
                os.replace(temp_file, SAVE_FILE)
            else:
                os.rename(temp_file, SAVE_FILE)
                
            log_to_console("Results saved successfully while preserving all existing data")
        except Exception as e:
            log_to_console(f"Error saving results: {e}")
    
    # Use thread pool for async saving
    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(save_task)

def delete_offline_onu(olt_ip, port, onu_id, mac_address):
    """Delete an offline ONU from saved data - FIXED VERSION"""
    try:
        log_to_console(f"Attempting to delete: OLT={olt_ip}, Port={port}, ONU_ID={onu_id}, MAC={mac_address}")
        
        # Ensure port is a string (since JSON keys are strings)
        port_str = str(port)
        
        # Load current data
        if not os.path.exists(SAVE_FILE):
            log_to_console("No saved data file found")
            return False, "No saved data file found"
        
        with open(SAVE_FILE, "r") as f:
            data = json.load(f)
        
        log_to_console(f"Data loaded. OLT {olt_ip} exists: {olt_ip in data}")
        
        # Check if OLT exists
        if olt_ip not in data:
            log_to_console(f"OLT {olt_ip} not found in data")
            return False, "OLT not found in saved data"
        
        log_to_console(f"Ports for OLT {olt_ip}: {list(data[olt_ip].keys())}")
        
        # Check if port exists - now using string version
        if port_str not in data[olt_ip]:
            log_to_console(f"Port {port_str} not found in OLT {olt_ip}")
            return False, f"Port {port} not found in saved data"
        
        # Find and remove the specific ONU
        updated_onu_list = []
        removed_onu = None
        found = False
        
        for onu in data[olt_ip][port_str]:
            # Try multiple ways to identify the ONU
            current_id = str(onu.get("ID") or onu.get("onu_id") or "")
            current_mac = onu.get("Mac address") or onu.get("mac", "")
            current_status = onu.get("Status", "")
            
            log_to_console(f"Checking ONU: ID={current_id}, MAC={current_mac}, Status={current_status}")
            
            # Clean MAC addresses for comparison
            clean_current_mac = current_mac.lower().replace(":", "").replace("-", "")
            clean_target_mac = mac_address.lower().replace(":", "").replace("-", "")
            
            # Check if this is the ONU we want to delete
            # Match by ONU ID AND MAC address to be more precise
            id_match = (current_id == str(onu_id))
            mac_match = (clean_current_mac == clean_target_mac)
            status_match = current_status == "🔴"
            
            if id_match and mac_match and status_match:
                log_to_console(f"Found ONU to delete: {onu}")
                removed_onu = onu
                found = True
                continue  # Skip this ONU (remove it)
            else:
                updated_onu_list.append(onu)
        
        if not found:
            log_to_console(f"No matching offline ONU found with ID={onu_id} and MAC={mac_address}")
            # Try a less strict search for debugging
            for onu in data[olt_ip][port_str]:
                current_id = str(onu.get("ID") or onu.get("onu_id") or "")
                current_mac = onu.get("Mac address") or onu.get("mac", "")
                log_to_console(f"Available ONU on port {port_str}: ID={current_id}, MAC={current_mac}")
            return False, "ONU not found in saved data or not offline"
        
        # Update the data
        data[olt_ip][port_str] = updated_onu_list
        
        # Remove empty ports
        if not data[olt_ip][port_str]:
            del data[olt_ip][port_str]
        
        # Remove empty OLT entries
        if not data[olt_ip]:
            del data[olt_ip]
        
        # Save updated data
        with open(SAVE_FILE, "w") as f:
            json.dump(data, f, indent=2)
        
        # Update cache
        st.session_state.cached_results = data
        st.session_state.cached_mtime = time.time()
        
        # Also remove from session state (using string port)
        if (olt_ip in st.session_state.monitoring_results and 
            port_str in st.session_state.monitoring_results[olt_ip]):
            
            updated_session_list = []
            for onu in st.session_state.monitoring_results[olt_ip][port_str]:
                current_id = str(onu.get("ID") or onu.get("onu_id") or "")
                current_mac = onu.get("Mac address") or onu.get("mac", "")
                current_status = onu.get("Status", "")
                
                clean_current_mac = current_mac.lower().replace(":", "").replace("-", "")
                clean_target_mac = mac_address.lower().replace(":", "").replace("-", "")
                
                if not (current_id == str(onu_id) and 
                       clean_current_mac == clean_target_mac and
                       current_status == "🔴"):
                    updated_session_list.append(onu)
            
            st.session_state.monitoring_results[olt_ip][port_str] = updated_session_list
        
        log_to_console(f"Successfully deleted offline ONU {onu_id} from OLT {olt_ip}, Port {port_str}")
        
        # Create log entry for deletion
        if removed_onu:
            name = removed_onu.get("Name", "Unknown")
            olt_name = get_olt_name_by_ip(olt_ip)
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            log_entry = {
                "timestamp": timestamp,
                "message": f"Deleted offline ONU: {name} (ID: {onu_id}, MAC: {mac_address}) from {olt_name} (Port {port})",
                "type": "deletion",
                "olt_name": olt_name,
                "olt_ip": olt_ip,
                "port": port_str,
                "onu_id": onu_id,
                "mac": mac_address,
                "name": name
            }
            
            # Save to movement logs
            logs = load_movement_logs()
            logs.append(log_entry)
            save_movement_logs([log_entry])
        
        return True, f"Successfully deleted offline ONU {onu_id} from Port {port}"
        
    except Exception as e:
        log_to_console(f"Error deleting ONU: {e}")
        return False, f"Error deleting ONU: {str(e)}"

def schedule_save(results):
    """Schedule a save operation with debouncing"""
    current_time = time.time()
    
    # Cancel previous timer if exists
    if st.session_state.save_timer:
        try:
            st.session_state.save_timer.cancel()
        except:
            pass
    
    # Add to queue
    st.session_state.save_queue.append((current_time, results))
    
    # If queue is large or enough time has passed, save immediately
    if (len(st.session_state.save_queue) >= SAVE_BATCH_SIZE or 
        current_time - st.session_state.last_save_time > SAVE_DEBOUNCE_TIME):
        save_results_async(results)
        st.session_state.last_save_time = current_time
        st.session_state.save_queue = []
    else:
        # Schedule delayed save
        def delayed_save():
            time.sleep(SAVE_DEBOUNCE_TIME)
            if st.session_state.save_queue:
                latest_time, latest_results = st.session_state.save_queue[-1]
                save_results_async(latest_results)
                st.session_state.last_save_time = latest_time
                st.session_state.save_queue = []
        
        st.session_state.save_timer = threading.Timer(SAVE_DEBOUNCE_TIME, delayed_save)
        st.session_state.save_timer.daemon = True
        st.session_state.save_timer.start()

def search_in_json(search_query):
    """Search for MAC address or name across all OLTs in JSON file and return (olt_ip, port, onu_data)"""
    previous_results = load_previous_results()
    
    if not previous_results:
        return None, None, None
    
    search_query = search_query.lower().strip()
    
    for olt_ip, olt_data in previous_results.items():
        for port, onu_list in olt_data.items():
            for onu in onu_list:
                # Search by MAC address
                onu_mac = onu.get("Mac address", onu.get("mac", "")).lower().replace(":", "").replace("-", "")
                search_mac = search_query.lower().replace(":", "").replace("-", "")
                
                if onu_mac.startswith(search_mac) and len(onu_mac) - len(search_mac) <= 2:
                    return olt_ip, port, onu
                
                # Also check for exact match with colons
                onu_mac_colons = onu.get("Mac address", "").lower()
                if search_mac in onu_mac_colons.replace(":", ""):
                    return olt_ip, port, onu
                
                # Search by name
                onu_name = onu.get("Name", "").lower()
                if search_query in onu_name:
                    return olt_ip, port, onu
                
                # Search by partial name match (case insensitive)
                if search_query and onu_name and search_query in onu_name:
                    return olt_ip, port, onu
    
    return None, None, None

def parse_onu_data(response_text, port):
    lines = response_text.split('\n')
    onu_list = []
    for line in lines:
        line = line.strip()
        if re.match(r'^\d+\s+\d+\s+[0-9a-f:-]{10,}', line.lower()):
            parts = line.split()
            if len(parts) >= 3:
                onu_id = parts[1]
                mac = parts[2].lower().replace("-", ":")
                name = find_matching_name(mac, st.session_state.mac_name_map)
                onu_list.append({"onu_id": onu_id, "mac": mac, "signal": "", "name": name})
        elif re.match(r'^onu-\d+', line.lower()):
            parts = line.split()
            onu_id = parts[0].replace("onu-", "").strip()
            mac_match = re.search(r'([0-9a-f]{2}:[0-9a-f]{2}:[0-9a-f]{2}:[0-9a-f]{2}:[0-9a-f]{2}:[0-9a-f]{2})', line.lower())
            mac = mac_match.group(1).lower() if mac_match else "N/A"
            name = find_matching_name(mac, st.session_state.mac_name_map)
            onu_list.append({"onu_id": onu_id, "mac": mac, "signal": "", "name": name})
    return onu_list

async def get_full_command_output(reader, writer, command, max_pages=10):
    full_output = ""
    cmd = command + "\r\n"
    log_to_console(f">>> {cmd.strip()}")   # show command
    writer.write(cmd.encode())
    await writer.drain()

    for _ in range(max_pages):
        await asyncio.sleep(1)
        try:
            chunk = await asyncio.wait_for(reader.read(4096), timeout=2)
            if not chunk:
                break
            text = chunk.decode("utf-8", errors="ignore")
            log_to_console(text)  # print raw OLT output
            full_output += text
            if "epon#" in text or "#" in text or ">" in text:
                break
        except asyncio.TimeoutError:
            pass
    return full_output

async def get_onu_signal(reader, writer, port, onu_id):
    """Run signal command for specific ONU and return RX optical power"""
    try:
        command = f"show olt {port} onu {onu_id} ctc optical"
        output = await get_full_command_output(reader, writer, command)

        match = re.search(r'rx power\s+(-?\d+\.\d+)\s*d?Bm?', output, re.IGNORECASE)
        if match:
            return match.group(1) + " dBm"
        else:
            return "N/A"
    except Exception as e:
        log_to_console(f"Error getting ONU signal: {e}")
        return "N/A"

async def reboot_onu(host, username, password, olt_port, onu_id):
    """Reboot an ONU handling both CLI login flows and capturing logs"""
    writer = None
    log_messages = []

    try:
        log_messages.append("🔌 Connecting to OLT...")
        reader, writer = await asyncio.open_connection(host, 23)

        async def read_and_log(prompts=None):
            try:
                if prompts:
                    for p in prompts:
                        data = await reader.readuntil(p)
                        text = data.decode(errors="ignore")
                        log_to_console(text)
                        log_messages.append(text)
                        return text
                else:
                    data = await reader.read(4096)
                    text = data.decode(errors="ignore")
                    log_to_console(text)
                    log_messages.append(text)
                    return text
            except Exception:
                return ""

        # --- Login sequence ---
        # Read until Username prompt
        banner = await reader.readuntil(b"Username:")
        log_messages.append(banner.decode(errors="ignore"))
        await asyncio.sleep(0.5)

        # Send username
        writer.write((username + "\r\n").encode())
        await writer.drain()

        # Read until Password prompt
        prompt = await reader.readuntil(b"Password:")
        log_messages.append(prompt.decode(errors="ignore"))
        await asyncio.sleep(0.5)

        # Send password
        writer.write((password + "\r\n").encode())
        await writer.drain()

        # Wait for either successful login or direct prompt
        login_success = await reader.read(4096)
        login_text = login_success.decode(errors="ignore")
        log_messages.append(login_text)
        log_to_console(login_text)
        await asyncio.sleep(0.5)

        # --- Send reboot commands ---
        writer.write(f"olt {olt_port}\r\n".encode()); await writer.drain()
        await asyncio.sleep(1)
        await read_and_log()

        writer.write(f"onu {onu_id}\r\n".encode()); await writer.drain()
        await asyncio.sleep(1)
        await read_and_log()

        writer.write("ctc reboot\r\n".encode()); await writer.drain()
        await asyncio.sleep(2)
        confirmation = await read_and_log()

        # Some EPON CLIs auto-accept, others might show "Please wait..."
        if "please wait" in confirmation.lower() or "success" in confirmation.lower():
            log_messages.append("✅ Reboot command sent successfully")
            success = True
        else:
            log_messages.append("❌ Reboot command may not have been accepted")
            success = False
            
        writer.write(b"exit\r\nexit\r\nexit\r\n"); await writer.drain()
        await asyncio.sleep(1)

        writer.close()
        await writer.wait_closed()
        return success, "\n".join(log_messages)

    except asyncio.TimeoutError:
        log_messages.append("❌ Timeout! Device not responding.")
        return False, "\n".join(log_messages)
    except Exception as e:
        log_messages.append(f"❌ Error: {e}")
        return False, "\n".join(log_messages)
    finally:
        if writer:
            writer.close()
            await writer.wait_closed()

async def monitor_olt(host, username, password, olt_ports):
    results = {}
    writer = None
    try:
        reader, writer = await asyncio.open_connection(host, 23)

        banner = await reader.readuntil(b"Username:")
        log_to_console(banner.decode(errors='ignore'))
        writer.write((username + "\r\n").encode()); await writer.drain()

        prompt = await reader.readuntil(b"Password:")
        log_to_console(prompt.decode(errors='ignore'))
        writer.write((password + "\r\n").encode()); await writer.drain()

        await asyncio.sleep(1)

        for port in olt_ports:
            command = f"show olt online-onu {port}"
            full_output = await get_full_command_output(reader, writer, command)
            onu_list = parse_onu_data(full_output, port)

            table_data = []
            for onu in onu_list:
                onu_id = onu["onu_id"]
                mac = onu["mac"]
                name = onu["name"]

                signal = await get_onu_signal(reader, writer, port, onu_id)

                table_data.append({
                    "Status": "🟢",
                    "ID": onu_id,
                    "Name": name,
                    "Mac address": mac,
                    "Onu signal": signal
                })

            results[str(port)] = table_data

        return results
    except Exception as e:
        st.error(f"Error monitoring OLT: {e}")
        return {}
    finally:
        if writer:
            writer.close()
            await writer.wait_closed()

def initiate_reboot(olt_ip, port, onu_id):
    """Initiate the reboot process and store status in session state"""
    st.session_state.reboot_status = {
        "active": True, 
        "port": port, 
        "onu_id": onu_id,
        "olt_ip": olt_ip,
        "message": "Starting reboot process...",
        "success": None
    }

def initiate_delete(olt_ip, port, onu_id, mac):
    """Initiate the delete process for an offline ONU"""
    st.session_state.delete_confirm = {
        "active": True,
        "olt_ip": olt_ip,
        "port": port,
        "onu_id": onu_id,
        "mac": mac
    }

def execute_reboot():
    """Execute the reboot process that was initiated"""
    if st.session_state.reboot_status["active"] and st.session_state.reboot_status["success"] is None:
        status = st.session_state.reboot_status
        success, message = asyncio.run(reboot_onu(
            status["olt_ip"], 
            USERNAME, 
            PASSWORD, 
            status["port"], 
            status["onu_id"]
        ))
        
        st.session_state.reboot_status["success"] = success
        st.session_state.reboot_status["message"] = message
        log_to_console(f"Reboot result: {success}, Message: {message}")

def execute_delete():
    """Execute the delete process for an offline ONU"""
    if st.session_state.delete_confirm["active"]:
        status = st.session_state.delete_confirm
        success, message = delete_offline_onu(
            status["olt_ip"],
            status["port"],
            status["onu_id"],
            status["mac"]
        )
        
        # Reset delete confirmation
        st.session_state.delete_confirm["active"] = False
        
        # Show result
        if success:
            st.success(message)
        else:
            st.error(message)
        
        log_to_console(f"Delete result: {success}, Message: {message}")
        return success

def highlight_text(text, search_query, exact_match_only=False):
    """Highlight the exact search query in the text with the same arrangement"""
    if not search_query or not text:
        return text
    
    text_str = str(text)
    search_lower = search_query.lower()
    text_lower = text_str.lower()
    
    # Try to find the exact search query in the text (case insensitive)
    if search_lower in text_lower:
        # Find the start index of the match
        start_idx = text_lower.find(search_lower)
        end_idx = start_idx + len(search_query)
        
        # Extract the exact matched portion from the original text (preserving case)
        matched_text = text_str[start_idx:end_idx]
        
        # Replace only the matched portion with highlighted version
        before = text_str[:start_idx]
        after = text_str[end_idx:]
        return f"{before}<mark style='background-color: yellow;'>{matched_text}</mark>{after}"
    
    # For exact match only, return the original text without highlighting
    if exact_match_only:
        return text_str
    
    return text_str

def get_olt_name_by_ip(ip):
    """Get OLT name by IP address"""
    for olt_id, olt_info in OLT_DEVICES.items():
        if olt_info["ip"] == ip:
            return olt_info["name"]
    return "Unknown OLT"

def get_olt_by_ip(ip):
    """Get OLT choice by IP address"""
    for olt_id, olt_info in OLT_DEVICES.items():
        if olt_info["ip"] == ip:
            return olt_id
    return "1"

async def monitor_single_port(host, username, password, port):
    """Monitor a single port for online/offline comparison"""
    try:
        current_results = await monitor_olt(host, username, password, [port])
        return current_results.get(str(port), [])
    except Exception as e:
        st.error(f"Error monitoring port {port}: {e}")
        return []

def load_movement_logs():
    """Load movement logs from file"""
    try:
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, "r") as f:
                return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        log_to_console(f"Error loading movement logs: {e}")
        # Create backup of corrupted file
        if os.path.exists(LOG_FILE):
            backup_name = f"{LOG_FILE}.backup.{int(time.time())}"
            os.rename(LOG_FILE, backup_name)
            log_to_console(f"Created backup of corrupted log file: {backup_name}")
    return []

def save_movement_logs(logs):
    """Save movement logs to file, appending new logs without overwriting"""
    try:
        # Load existing logs
        existing_logs = load_movement_logs()
        
        # Append new logs (avoid duplicates by timestamp and message)
        for new_log in logs:
            if new_log not in existing_logs:
                existing_logs.append(new_log)
        
        # Keep only the last 1000 logs to prevent file from growing too large
        if len(existing_logs) > 1000:
            existing_logs = existing_logs[-1000:]
        
        # Save to file
        with open(LOG_FILE, "w") as f:
            json.dump(existing_logs, f, indent=2)
            
        log_to_console(f"Saved {len(logs)} new movement logs")
        return True
    except Exception as e:
        log_to_console(f"Error saving movement logs: {e}")
        return False

def detect_movements(current_results, previous_results, olt_ip):
    """Detect when ONUs move between ports and generate log entries with OLT name"""
    movements = []
    
    # Get OLT name
    olt_name = get_olt_name_by_ip(olt_ip)
    
    # Create a mapping of MAC addresses to their current status
    current_mac_map = {}
    for port, onu_list in current_results.items():
        for onu in onu_list:
            mac = onu.get("Mac address", onu.get("mac", "")).lower().replace(":", "").replace("-", "")
            if mac and mac != "n/a":
                current_mac_map[mac] = {
                    "olt_ip": olt_ip,
                    "olt_name": olt_name,
                    "port": port,
                    "status": onu.get("Status", "🟢"),
                    "name": onu.get("Name", ""),
                    "id": onu.get("ID", onu.get("onu_id", ""))
                }
    
    # Create a mapping of MAC addresses to their previous status
    previous_mac_map = {}
    if olt_ip in previous_results:
        for port, onu_list in previous_results[olt_ip].items():
            for onu in onu_list:
                mac = onu.get("Mac address", onu.get("mac", "")).lower().replace(":", "").replace("-", "")
                if mac and mac != "n/a":
                    previous_mac_map[mac] = {
                        "olt_ip": olt_ip,
                        "olt_name": olt_name,
                        "port": port,
                        "status": onu.get("Status", "🔴"),  # Assume offline in previous results
                        "name": onu.get("Name", ""),
                        "id": onu.get("ID", onu.get("onu_id", ""))
                    }
    
    # Check for movements
    for mac, current_info in current_mac_map.items():
        if mac in previous_mac_map:
            previous_info = previous_mac_map[mac]
            
            # If the ONU was offline before but is online now on a different port
            if (previous_info["status"] == "🔴" and 
                current_info["status"] == "🟢" and 
                previous_info["port"] != current_info["port"]):
                
                # Create log entry with OLT name
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                log_entry = {
                    "timestamp": timestamp,
                    "message": f"{current_info['name'] or 'Unknown'} (MAC: {mac}) moved from port {previous_info['port']} to port {current_info['port']} on {olt_name}",
                    "type": "movement",
                    "olt_name": olt_name,
                    "olt_ip": olt_ip,
                    "mac": mac,
                    "from_port": previous_info["port"],
                    "to_port": current_info["port"],
                    "name": current_info["name"]
                }
                movements.append(log_entry)
                log_to_console(f"Movement detected: {log_entry['message']}")
    
    # Check for duplicates (same MAC on multiple ports in current results)
    mac_count = {}
    for mac in current_mac_map:
        mac_count[mac] = mac_count.get(mac, 0) + 1
    
    for mac, count in mac_count.items():
        if count > 1:
            # Find all ports where this MAC appears
            ports = []
            for port, onu_list in current_results.items():
                for onu in onu_list:
                    onu_mac = onu.get("Mac address", onu.get("mac", "")).lower().replace(":", "").replace("-", "")
                    if onu_mac == mac:
                        ports.append(port)
            
            if ports:
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                name = current_mac_map[mac]["name"] or "Unknown"
                log_entry = {
                    "timestamp": timestamp,
                    "message": f"Duplicate detected: {name} (MAC: {mac}) appears on multiple ports on {olt_name}: {', '.join(ports)}",
                    "type": "duplicate",
                    "olt_name": olt_name,
                    "olt_ip": olt_ip,
                    "mac": mac,
                    "ports": ports,
                    "name": name
                }
                movements.append(log_entry)
                log_to_console(f"Duplicate detected: {log_entry['message']}")
    
    return movements

def show_logs_page():
    st.header("ONU Movement Logs")
    
    # Load logs from file
    logs = load_movement_logs()
    
    if not logs:
        st.info("No movement logs found yet. Run monitoring to detect ONU movements.")
        return
    
    # Filter options
    col1, col2, col3 = st.columns(3)
    with col1:
        log_type = st.selectbox("Filter by type", ["All", "Movement", "Duplicate", "Deletion"])
    with col2:
        olt_filter = st.selectbox("Filter by OLT", ["All OLTs"] + [OLT_DEVICES[olt]["name"] for olt in OLT_DEVICES])
    with col3:
        search_term = st.text_input("Search in logs")
    
    # Filter logs
    filtered_logs = logs
    if log_type != "All":
        filtered_logs = [log for log in filtered_logs if log["type"] == log_type.lower()]
    
    if olt_filter != "All OLTs":
        filtered_logs = [log for log in filtered_logs if log.get("olt_name") == olt_filter]
    
    if search_term:
        search_lower = search_term.lower()
        filtered_logs = [
            log for log in filtered_logs 
            if search_lower in log["message"].lower() or 
               search_lower in log.get("name", "").lower() or
               search_lower in log.get("mac", "").lower() or
               search_lower in log.get("olt_name", "").lower()
        ]
    
    # Display logs in reverse chronological order (newest first)
    filtered_logs.reverse()
    
    if not filtered_logs:
        st.info("No logs match your filters.")
        return
    
    # Display logs
    for log in filtered_logs:
        # Color code based on log type
        if log["type"] == "movement":
            icon = "🔄"
            color = "#e6f3ff"
        elif log["type"] == "duplicate":
            icon = "⚠️"
            color = "#fff3cd"
        elif log["type"] == "deletion":
            icon = "🗑️"
            color = "#f8d7da"
        else:
            icon = "📝"
            color = "#f8f9fa"
        
        with st.expander(f"{icon} {log['timestamp']} - {log['message']}"):
            st.markdown(f"<div style='background-color: {color}; padding: 10px; border-radius: 5px;'>", unsafe_allow_html=True)
            st.write(f"**Type:** {log['type']}")
            st.write(f"**OLT:** {log.get('olt_name', 'N/A')}")
            st.write(f"**MAC:** {log.get('mac', 'N/A')}")
            st.write(f"**Name:** {log.get('name', 'N/A')}")
            if log["type"] == "movement":
                st.write(f"**From port:** {log.get('from_port', 'N/A')}")
                st.write(f"**To port:** {log.get('to_port', 'N/A')}")
            elif log["type"] == "duplicate":
                st.write(f"**Ports:** {', '.join(log.get('ports', []))}")
            elif log["type"] == "deletion":
                st.write(f"**Port:** {log.get('port', 'N/A')}")
                st.write(f"**ONU ID:** {log.get('onu_id', 'N/A')}")
            st.markdown("</div>", unsafe_allow_html=True)
    
    # Download button
    if st.button("Download Logs as CSV"):
        df = pd.DataFrame(filtered_logs)
        csv = df.to_csv(index=False)
        st.download_button(
            label="Download CSV",
            data=csv,
            file_name="onu_movement_logs.csv",
            mime="text/csv"
        )

# ---------------- STREAMLIT APP ----------------
st.title("DUMBOLT for CDATA F series olt")

# Show config info in sidebar
st.sidebar.info(f"Loaded configuration from config.json\nOLTs configured: {len(OLT_DEVICES)}")

# Load MAC address list on first run
if not st.session_state.mac_name_map:
    st.session_state.mac_name_map = load_mac_address_list(MAC_ADDRESS_FILE)

# Handle delete confirmation if active
if st.session_state.delete_confirm["active"]:
    status = st.session_state.delete_confirm
    olt_name = get_olt_name_by_ip(status["olt_ip"])
    
    st.warning(f"Are you sure you want to delete this offline ONU?")
    st.write(f"**OLT:** {olt_name}")
    st.write(f"**Port:** {status['port']}")
    st.write(f"**ONU ID:** {status['onu_id']}")
    st.write(f"**MAC:** {status['mac']}")
    
    col1, col2, col3 = st.columns([1, 1, 3])
    with col1:
        if st.button("✅ Yes, Delete", key="confirm_delete"):
            success = execute_delete()
            if success:
                st.rerun()
    with col2:
        if st.button("❌ Cancel", key="cancel_delete"):
            st.session_state.delete_confirm["active"] = False
            st.rerun()
    
    st.stop()

# Handle reboot execution if a reboot was initiated
if st.session_state.reboot_status["active"] and st.session_state.reboot_status["success"] is None:
    with st.spinner("Rebooting ONU, please wait..."):
        execute_reboot()

# Show reboot status if a reboot was completed (minimal UI)
if st.session_state.reboot_status["active"] and st.session_state.reboot_status["success"] is not None:
    status = st.session_state.reboot_status
    if status["success"]:
        st.success(f"✅ ONU {status['onu_id']} on Port {status['port']} rebooted!")
    else:
        st.error(f"❌ Failed to reboot ONU {status['onu_id']} on Port {status['port']}")
    
    if st.button("Continue"):
        st.session_state.reboot_status = {"active": False, "port": None, "onu_id": None, "message": "", "success": None}
        st.rerun()
    
    st.stop()

# Navigation
st.sidebar.header("Navigation")
page = st.sidebar.radio("Go to", ["Monitoring", "Logs"])

if page == "Logs":
    show_logs_page()
    st.stop()

# Search functionality
st.sidebar.header("🔍 Search ONUs")
search_query = st.sidebar.text_input("Search by MAC address or Name", value=st.session_state.search_query,
                                    placeholder="Enter MAC address or Name")

# Reload MAC address list button
if st.sidebar.button("Reload MAC Address List"):
    st.session_state.mac_name_map = load_mac_address_list(MAC_ADDRESS_FILE)
    update_existing_results_with_names()
    st.sidebar.success(f"Reloaded {len(st.session_state.mac_name_map)} MAC addresses and updated existing results")

# Fast MAC address or name search
if search_query and search_query != st.session_state.search_query:
    st.session_state.search_query = search_query
    st.session_state.search_loading = False
    
    # Immediately search in JSON file
    olt_ip, port, onu_data = search_in_json(search_query)
    
    if olt_ip and port and onu_data:
        st.session_state.search_olt_ip = olt_ip
        st.session_state.search_port = port
        # Store with port as key, not OLT IP
        st.session_state.search_results = {port: [onu_data]}
        st.session_state.search_loading = True
        # Set the OLT choice to match the found OLT
        st.session_state.olt_choice = get_olt_by_ip(olt_ip)
    else:
        st.sidebar.warning("MAC address or name not found in saved data")
        st.session_state.search_results = {}
        st.session_state.search_loading = False

# Main monitoring interface
olt_choice = st.selectbox(
    "Select OLT to monitor",
    options=list(OLT_DEVICES.keys()),
    format_func=lambda x: f"{OLT_DEVICES[x]['name']}",
    key="olt_choice"
)

# If we have a search result and need to monitor that port
if st.session_state.search_loading and st.session_state.search_port and st.session_state.search_olt_ip:
    olt_ip = st.session_state.search_olt_ip
    port = st.session_state.search_port
    olt_name = get_olt_name_by_ip(olt_ip)
    
    st.write(f"### Port {port} on {olt_name}")
    
    # Show the saved results immediately from JSON
    previous_results = load_previous_results()
    olt_previous = previous_results.get(olt_ip, {})
    port_previous = olt_previous.get(port, [])
    
    if port_previous:
        # Display the found ONU immediately
        found_onu = None
        for onu in port_previous:
            onu_mac = onu.get("Mac address", "").lower().replace(":", "").replace("-", "")
            search_term = st.session_state.search_query.lower().replace(":", "").replace("-", "")
            onu_name = onu.get("Name", "").lower()
            
            # Check if it matches by MAC or name
            if (onu_mac.startswith(search_term) and len(onu_mac) - len(search_term) <= 2) or search_term in onu_name:
                found_onu = onu
                break
        
        if found_onu:
            headers = ["Status", "ID", "Name", "Mac address", "Onu signal", "Action"]
            header_cols = st.columns([1, 1, 2, 3, 2, 2])

            for i, col in enumerate(header_cols):
                col.write(f"**{headers[i]}**")

            cols = st.columns([1, 1, 2, 3, 2, 2])
            with cols[0]:
                st.write("⏳")
            with cols[1]:
                st.write(found_onu.get("ID", found_onu.get("onu_id", "N/A")))
            with cols[2]:
                name_html = highlight_text(found_onu.get("Name", ""), st.session_state.search_query, exact_match_only=True)
                st.markdown(name_html, unsafe_allow_html=True)
            with cols[3]:
                mac_html = highlight_text(found_onu.get("Mac address", found_onu.get("mac", "N/A")), st.session_state.search_query, exact_match_only=True)
                st.markdown(mac_html, unsafe_allow_html=True)
            with cols[4]:
                st.write("⏳")
            with cols[5]:
                st.write("")

            st.markdown("---")
    
    # Start monitoring in the background
    with st.spinner(f"Scanning Port {port}..."):
        current_port_data = asyncio.run(monitor_single_port(olt_ip, USERNAME, PASSWORD, int(port)))
        
        # Update the previous results with current status
        previous_results = load_previous_results()
        olt_previous = previous_results.get(olt_ip, {})
        port_previous = olt_previous.get(port, [])
        
        current_macs = {onu["Mac address"] for onu in current_port_data}
        final_port_data = list(current_port_data)

        for prev_onu in port_previous:
            prev_mac = prev_onu.get("Mac address", prev_onu.get("mac", ""))
            if prev_mac not in current_macs:
                offline_onu = prev_onu.copy()
                offline_onu["Status"] = "🔴"
                if "mac" in offline_onu:
                    offline_onu["Mac address"] = offline_onu.pop("mac")
                if "onu_id" in offline_onu:
                    offline_onu["ID"] = offline_onu.pop("onu_id")
                if "Onu signal" not in offline_onu:
                    offline_onu["Onu signal"] = "N/A"
                # Ensure name field exists
                if "name" not in offline_onu:
                    offline_onu["name"] = find_matching_name(offline_onu.get("Mac address", ""), st.session_state.mac_name_map)
                final_port_data.append(offline_onu)
        
        # Update session state with final results
        if olt_ip not in st.session_state.monitoring_results:
            st.session_state.monitoring_results[olt_ip] = {}
        st.session_state.monitoring_results[olt_ip][port] = final_port_data
        
        # Update search results
        exact_search_results = {}
        for onu in final_port_data:
            mac_match = st.session_state.search_query.lower() in onu.get("Mac address", "").lower().replace(":", "").replace("-", "")
            name_match = st.session_state.search_query.lower() in onu.get("Name", "").lower()
            if mac_match or name_match:
                if port not in exact_search_results:
                    exact_search_results[port] = []
                exact_search_results[port].append(onu)
        
        st.session_state.search_results = exact_search_results
        st.session_state.search_loading = False
        
        # Save results asynchronously
        previous_results[olt_ip] = st.session_state.monitoring_results[olt_ip]
        schedule_save(previous_results)
        
        st.rerun()

st.write("### Select Ports to Monitor")
selected_ports = []
cols = st.columns(8)
for i, col in enumerate(cols, start=1):
    if col.checkbox(f"{i}", key=f"port_{i}"):
        selected_ports.append(i)

if st.button("Run Monitoring", key="run_monitoring"):
    olt_ports = selected_ports if selected_ports else list(range(1, 9))
    olt = OLT_DEVICES[olt_choice]
    st.write(f"### {olt['name']}")

    previous_results = load_previous_results()
    olt_previous = previous_results.get(olt["ip"], {})

    # Clear any existing loading messages
    st.session_state.ports_loaded = set()

    with st.spinner("Monitoring OLT..."):
        current_results = asyncio.run(monitor_olt(olt["ip"], USERNAME, PASSWORD, olt_ports))

    if not current_results:
        st.error("No results found or connection failed.")
    else:
        final_results = {}

        for port in olt_ports:
            port_str = str(port)
            current_port_data = current_results.get(port_str, [])
            previous_port_data = olt_previous.get(port_str, [])

            current_macs = {onu["Mac address"] for onu in current_port_data}
            final_port_data = list(current_port_data)

            for prev_onu in previous_port_data:
                prev_mac = prev_onu.get("Mac address", prev_onu.get("mac", ""))
                if prev_mac not in current_macs:
                    offline_onu = prev_onu.copy()
                    offline_onu["Status"] = "🔴"
                    if "mac" in offline_onu:
                        offline_onu["Mac address"] = offline_onu.pop("mac")
                    if "onu_id" in offline_onu:
                        offline_onu["ID"] = offline_onu.pop("onu_id")
                    if "Onu signal" not in offline_onu:
                        offline_onu["Onu signal"] = "N/A"
                    # Ensure name field exists
                    if "name" not in offline_onu:
                        offline_onu["name"] = find_matching_name(offline_onu.get("Mac address", ""), st.session_state.mac_name_map)
                    final_port_data.append(offline_onu)

            final_results[port_str] = final_port_data
            st.session_state.ports_loaded.add(port_str)

        # Store results in session state for persistence
        st.session_state.monitoring_results[olt["ip"]] = final_results
        
        # Detect movements and duplicates with OLT name
        movements = detect_movements(final_results, {olt["ip"]: olt_previous}, olt["ip"])
        if movements:
            st.session_state.movement_logs.extend(movements)
            save_movement_logs(movements)
            for movement in movements:
                if movement["type"] == "movement":
                    st.warning(movement["message"])
                else:
                    st.error(movement["message"])
        
        previous_results[olt["ip"]] = final_results
        
        # Save results asynchronously with debouncing
        schedule_save(previous_results)
        
        # Update search results if there's a search query (exact matches only)
        if search_query:
            exact_search_results = {}
            for port_str, onu_list in final_results.items():
                for onu in onu_list:
                    mac_match = search_query.lower() in onu.get("Mac address", "").lower().replace(":", "").replace("-", "")
                    name_match = search_query.lower() in onu.get("Name", "").lower()
                    if mac_match or name_match:
                        if port_str not in exact_search_results:
                            exact_search_results[port_str] = []
                        exact_search_results[port_str].append(onu)
            
            st.session_state.search_results = exact_search_results
        
        st.success("Monitoring completed! Results are being saved...")
        st.rerun()

# Display results after monitoring
if st.session_state.monitoring_results and not st.session_state.search_loading:
    olt = OLT_DEVICES[olt_choice]
    olt_results = st.session_state.monitoring_results.get(olt["ip"], {})
    
    # If there's a search query, only show ports with matches
    display_ports = {}
    if search_query and st.session_state.search_results:
        display_ports = st.session_state.search_results
    else:
        display_ports = olt_results
    
    for port_str, final_port_data in display_ports.items():
        # Skip if port_str is not a valid port number
        if not port_str.isdigit():
            continue
            
        # Only show ports that were selected for monitoring
        if int(port_str) in selected_ports or not selected_ports:
            st.subheader(f"Port {port_str}")
            if final_port_data:
                headers = ["Status", "ID", "Name", "Mac address", "Onu signal", "Action"]
                header_cols = st.columns([1, 1, 2, 3, 2, 2])

                for i, col in enumerate(header_cols):
                    col.write(f"**{headers[i]}**")

                for idx, onu in enumerate(final_port_data):
                    cols = st.columns([1, 1, 2, 3, 2, 2])
                    with cols[0]:
                        status = onu.get("Status", "⏳")
                        st.write(status)
                    with cols[1]:
                        st.write(onu.get("ID", onu.get("onu_id", "N/A")))
                    with cols[2]:
                        # Highlight search matches in name
                        name_html = highlight_text(onu.get("Name", ""), search_query, exact_match_only=True)
                        st.markdown(name_html, unsafe_allow_html=True)
                    with cols[3]:
                        # Highlight search matches in MAC address
                        mac_html = highlight_text(onu.get("Mac address", onu.get("mac", "N/A")), search_query, exact_match_only=True)
                        st.markdown(mac_html, unsafe_allow_html=True)
                    with cols[4]:
                        st.write(onu.get("Onu signal", "N/A"))
                    with cols[5]:
                        if onu.get("Status") == "🟢":
                            # Create unique key for reboot button
                            reboot_key = f"reboot_{olt['ip']}_{port_str}_{onu.get('ID', onu.get('onu_id', ''))}_{onu.get('Mac address', onu.get('mac', ''))}_{idx}"
                            if st.button(f"Reboot", key=reboot_key):
                                initiate_reboot(olt["ip"], int(port_str), onu.get("ID", onu.get("onu_id", "")))
                                st.rerun()
                        elif onu.get("Status") == "🔴":
                            # Add delete button for offline ONUs
                            mac = onu.get("Mac address", onu.get("mac", "N/A"))
                            onu_id = onu.get("ID", onu.get("onu_id", ""))
                            
                            # Create unique key with OLT IP, port, ONU ID, MAC, and index
                            # Use cleaned MAC without colons for key
                            clean_mac = mac.replace(":", "").replace("-", "")[:8] if mac else str(idx)
                            delete_key = f"delete_{olt['ip']}_{port_str}_{onu_id}_{clean_mac}_{idx}"
                            
                            if st.button(f"🗑️ Delete", key=delete_key):
                                initiate_delete(olt["ip"], int(port_str), onu_id, mac)
                                st.rerun()
                        else:
                            st.write("")

                st.markdown("---")
            else:
                st.info("No ONUs found on this port")