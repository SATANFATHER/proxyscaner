import configparser
import masscan
import json
import asyncio
import sys
import logging
import os # Added for path operations

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

try:
    from proxy_tester import test_socks4_proxy, test_socks5_proxy, test_http_proxy
except ImportError:
    logging.error("proxy_tester.py not found. Please ensure it's in the same directory.")
    if "proxy_tester" not in sys.modules:
        # This dummy creation is more for robustness during isolated execution
        # In a full deployment, all files should be present.
        with open("proxy_tester.py", "w") as f_dummy:
            f_dummy.write("""
import asyncio
async def test_socks4_proxy(ip, port, url, timeout): return (False, "Dummy: Not Implemented", "SOCKS4")
async def test_socks5_proxy(ip, port, url, timeout): return (False, "Dummy: Not Implemented", "SOCKS5")
async def test_http_proxy(ip, port, url, timeout, is_https_tunnel=False): return (False, "Dummy: Not Implemented", "HTTP/S")
""")
            logging.info("Created a dummy proxy_tester.py. Functionality will be limited.")
            from proxy_tester import test_socks4_proxy, test_socks5_proxy, test_http_proxy


def load_config(config_file='config.ini'):
    # Ensure parser handles inline comments correctly
    config = configparser.ConfigParser(inline_comment_prefixes=(';', '#'))
    if not os.path.exists(config_file) or os.path.getsize(config_file) == 0:
        logging.warning(f"Config file '{config_file}' not found or empty. Using default fallback values.")
        default_config = {
            'scan': {
                'ip_range': '127.0.0.1', # Fallback if iprange.txt is also empty/missing
                'scan_speed': '1000',
                'timeout': '5',
                'ports': '80,443,1080,3128,8080,8888,9999',
                'test_url': 'http://httpbin.org/ip',
                'https_test_url': 'https://api.ipify.org',
                'masscan_args': '',
                'ip_range_file': 'iprange.txt' # New default entry
            }
        }
        config.read_dict(default_config)
    else:
        config.read(config_file)
        # Ensure default for ip_range_file if not in existing file for backward compatibility
        if not config.has_option('scan', 'ip_range_file'):
            config.set('scan', 'ip_range_file', 'iprange.txt')
        if not config.has_option('scan', 'ip_range'): # Ensure fallback ip_range is there
            config.set('scan', 'ip_range', '127.0.0.1')


    return config

def get_ip_ranges_to_scan(config):
    """
    Determines the list of IP ranges to scan.
    Reads from the file specified in 'ip_range_file' if it exists and is not empty.
    Otherwise, uses the 'ip_range' from the config as a single-element list.
    """
    ip_ranges = []
    # Get the raw filename and clean it, just in case inline_comment_prefixes doesn't catch all edge cases
    # or if the value itself had a semicolon intended not as a comment.
    # However, with inline_comment_prefixes set, config.get() should return clean values.
    raw_range_file_name = config.get('scan', 'ip_range_file', fallback='iprange.txt')
    range_file_name = raw_range_file_name.split(';')[0].split('#')[0].strip()


    if os.path.exists(range_file_name) and os.path.getsize(range_file_name) > 0:
        logging.info(f"Reading IP ranges from file: '{range_file_name}' (raw value from config for filename: '{raw_range_file_name}')")
        with open(range_file_name, 'r') as f:
            for line in f:
                line = line.strip() # Clean each line from file
                if line and not line.startswith('#'): # Ignore empty lines and comments
                    ip_ranges.append(line)
        if not ip_ranges: # After reading file
            logging.warning(f"IP range file '{range_file_name}' was read, but it was empty or only contained comments. No ranges loaded from file.")
    else: # File does not exist or is empty
        logging.info(f"IP range file '{range_file_name}' not found or is zero size. (Raw filename from config: '{raw_range_file_name}')")

    # Fallback to single ip_range from config if ip_ranges list is still empty
    if not ip_ranges:
        fallback_range_raw = config.get('scan', 'ip_range', fallback='127.0.0.1')
        # Clean the fallback range value as well
        fallback_range = fallback_range_raw.split(';')[0].split('#')[0].strip()

        logging.info(f"No valid IP ranges loaded from file. Using fallback IP range from config: '{fallback_range}' (raw value from config: '{fallback_range_raw}')")
        if fallback_range: # Ensure it's not empty after stripping
            ip_ranges.append(fallback_range)
        else:
            logging.error("Fallback IP range from config is also empty after stripping. Cannot proceed without scan ranges.")
            # amain() will catch empty ip_ranges_to_scan and exit

    return ip_ranges

def scan_ports(ip_range, ports_list, scan_rate_str, masscan_args_str):
    mas = masscan.PortScanner()
    ports_str = ','.join(map(str, ports_list))
    effective_args = f'--rate {scan_rate_str}'
    if masscan_args_str:
        effective_args = masscan_args_str if '--rate' in masscan_args_str else f'{masscan_args_str} --rate {scan_rate_str}'

    logging.info(f"Scanning {ip_range} for ports {ports_str} with effective masscan args: '{effective_args}'")

    try:
        scan_result_json_str = mas.scan(ip_range, ports=ports_str, arguments=effective_args)
        if isinstance(scan_result_json_str, str):
            scan_result = json.loads(scan_result_json_str)
        else:
            scan_result = scan_result_json_str
        return scan_result
    except masscan.PortScannerError as e:
        logging.error(f"Masscan execution error for range {ip_range}: {e}. Is masscan installed and in PATH?")
        return None
    except json.JSONDecodeError as e:
        logging.error(f"Failed to decode masscan JSON output for range {ip_range}: {e}. Output was: {scan_result_json_str}")
        return None
    except Exception as e:
        logging.error(f"An unexpected error occurred during scan for range {ip_range}: {e}")
        return None

async def test_single_proxy_candidate(ip, port, config):
    test_url = config.get('scan', 'test_url')
    timeout_seconds = config.getint('scan', 'timeout')
    https_test_url = config.get('scan', 'https_test_url', fallback='https://api.ipify.org')

    tasks = []
    if port == 1080:
        tasks.append(test_socks4_proxy(ip, port, test_url, timeout_seconds))
        tasks.append(test_socks5_proxy(ip, port, test_url, timeout_seconds))

    tasks.append(test_http_proxy(ip, port, test_url, timeout_seconds, is_https_tunnel=False))
    tasks.append(test_http_proxy(ip, port, https_test_url, timeout_seconds, is_https_tunnel=True))

    test_results = await asyncio.gather(*tasks, return_exceptions=True)

    successful_tests_info = []
    for res in test_results:
        if isinstance(res, Exception):
            logging.debug(f"Exception while testing {ip}:{port} - {res}")
        elif res and res[0] is True:
            protocol_type = res[2]
            response_time_ms = res[1]
            successful_tests_info.append({'protocol': protocol_type, 'time': response_time_ms})
        elif res and res[0] is False:
            logging.debug(f"FAILED: {ip}:{port} as {res[2]} - {res[1]}") # Protocol type is res[2]

    return successful_tests_info


async def process_scan_results(scan_data_list, config_main): # scan_data_list from multiple ranges
    if not scan_data_list:
        logging.info("No scan data received (all ranges might have failed or returned empty).")
        return []

    open_ports_candidates = []
    for scan_data in scan_data_list:
        if not scan_data or 'scan' not in scan_data or not scan_data.get('scan'):
            logging.debug("Empty or invalid scan data block skipped.")
            continue
        for ip_addr, details in scan_data['scan'].items():
            if 'tcp' in details:
                for port_num_str in details['tcp'].keys():
                    try:
                        port_num = int(port_num_str)
                        open_ports_candidates.append({'ip': ip_addr, 'port': port_num})
                    except ValueError:
                        logging.warning(f"Could not parse port number: {port_num_str} for IP {ip_addr}")

    if not open_ports_candidates:
        logging.info("No open ports found by masscan across all scanned ranges, or ports could not be parsed.")
        return []

    # Remove duplicates that might arise if ranges overlap or same IP:port is listed multiple times
    # Convert list of dicts to list of tuples of items, then to set to get unique, then back to list of dicts
    unique_candidates_tuples = {tuple(sorted(d.items())) for d in open_ports_candidates}
    unique_candidates = [dict(t) for t in unique_candidates_tuples]

    if len(unique_candidates) < len(open_ports_candidates):
        logging.info(f"Removed {len(open_ports_candidates) - len(unique_candidates)} duplicate IP/port candidates.")

    logging.info(f"Found {len(unique_candidates)} unique open IP/port combinations from {len(open_ports_candidates)} total. Starting proxy validation...")

    validation_tasks = [test_single_proxy_candidate(cand['ip'], cand['port'], config_main) for cand in unique_candidates]
    all_results = await asyncio.gather(*validation_tasks, return_exceptions=True)

    final_working_proxies = []
    for i, candidate in enumerate(unique_candidates):
        results_for_candidate = all_results[i]
        if isinstance(results_for_candidate, Exception):
            logging.error(f"Error in test_single_proxy_candidate for {candidate['ip']}:{candidate['port']}: {results_for_candidate}")
            continue
        if results_for_candidate:
            for success_info in results_for_candidate:
                final_working_proxies.append({
                    'ip': candidate['ip'],
                    'port': candidate['port'],
                    'protocol': success_info['protocol'],
                    'response_time_ms': success_info['time']
                })
                # Log individual successful proxy finding here for immediate feedback during long runs
                logging.info(f"VALIDATED: {candidate['ip']}:{candidate['port']} as {success_info['protocol']} (Time: {success_info['time']:.2f}ms)")

    return final_working_proxies

async def amain():
    try:
        import aiohttp_socks
    except ImportError:
        logging.warning("aiohttp-socks not found. Attempting to install...")
        import subprocess
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "aiohttp-socks"])
            logging.info("aiohttp-socks installed successfully.")
        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to install aiohttp-socks: {e}. SOCKS proxy testing will fail.")

    config = load_config()

    # Get IP ranges to scan
    ip_ranges_to_scan = get_ip_ranges_to_scan(config)
    if not ip_ranges_to_scan:
        logging.error("No IP ranges to scan. Please check config.ini or iprange.txt. Exiting.")
        return

    logging.info(f"Target IP ranges for scanning: {ip_ranges_to_scan}")

    scan_speed = config.get('scan', 'scan_speed')
    ports_str = config.get('scan', 'ports')
    ports_list = [int(p.strip()) for p in ports_str.split(',') if p.strip().isdigit()]
    masscan_custom_args = config.get('scan', 'masscan_args', fallback='')

    all_scan_outputs = []
    for ip_range in ip_ranges_to_scan:
        logging.info(f"Starting scan for IP range: {ip_range}")
        scan_output = scan_ports(ip_range, ports_list, scan_speed, masscan_custom_args)
        if scan_output:
            all_scan_outputs.append(scan_output)

    working_proxies = await process_scan_results(all_scan_outputs, config)

    logging.info(f"\n--- Summary of Working Proxies ({len(working_proxies)}) ---")
    if working_proxies:
        working_proxies.sort(key=lambda p: (p['ip'], p['port'], p['protocol']))

        with open("results.txt", "w") as f:
            for proxy in working_proxies:
                logging.info(f"  SAVING: {proxy['ip']}:{proxy['port']} # {proxy['protocol']} (Time: {proxy['response_time_ms']:.2f}ms)")
                f.write(f"{proxy['ip']}:{proxy['port']} # {proxy['protocol']}\n")
        logging.info(f"Working proxies saved to results.txt (Total: {len(working_proxies)})")
    else:
        logging.info("No working proxies found after validation across all ranges.")
        with open("results.txt", "w") as f:
            f.write("# No working proxies found during this scan.\n")
        logging.info("results.txt updated to reflect no working proxies found.")

if __name__ == '__main__':
    asyncio.run(amain())
