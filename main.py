import configparser
import masscan
import json
import asyncio
import sys
import logging
import time # For basic timing if needed, though proxy_tester handles its own

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

try:
    from proxy_tester import test_socks4_proxy, test_socks5_proxy, test_http_proxy
except ImportError:
    logging.error("proxy_tester.py not found. Please ensure it's in the same directory.")
    if "proxy_tester" not in sys.modules:
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
    config = configparser.ConfigParser()
    if not config.read(config_file):
        logging.warning(f"Config file '{config_file}' not found or empty. Using default fallback values.")
        default_config = {
            'scan': {
                'ip_range': '127.0.0.1',
                'scan_speed': '1000',
                'timeout': '5', # Proxy test timeout
                'ports': '80,443,1080,3128,8080,8888,9999', # Common proxy ports
                'test_url': 'http://httpbin.org/ip',
                'https_test_url': 'https://api.ipify.org', # Added for HTTPS tunnel test
                'masscan_args': ''
            }
        }
        config.read_dict(default_config)
    return config

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
        logging.error(f"Masscan execution error: {e}. Is masscan installed and in PATH?")
        return None
    except json.JSONDecodeError as e:
        logging.error(f"Failed to decode masscan JSON output: {e}. Output was: {scan_result_json_str}")
        return None
    except Exception as e:
        logging.error(f"An unexpected error occurred during scan: {e}")
        return None

async def test_single_proxy_candidate(ip, port, config):
    test_url = config.get('scan', 'test_url')
    timeout_seconds = config.getint('scan', 'timeout')
    https_test_url = config.get('scan', 'https_test_url', fallback='https://api.ipify.org') # Ensure this is used

    tasks = []
    # Common SOCKS ports like 1080, 1081 etc.
    # For now, only testing 1080 specifically for SOCKS, can be expanded.
    if port == 1080:
        tasks.append(test_socks4_proxy(ip, port, test_url, timeout_seconds))
        tasks.append(test_socks5_proxy(ip, port, test_url, timeout_seconds))

    # Test HTTP/HTTPS for all specified ports
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
            # Logging successful test here can be verbose if many proxies are found
            # logging.info(f"SUCCESS: {ip}:{port} works as {protocol_type} (Time: {response_time_ms:.2f}ms)")
        elif res and res[0] is False:
            logging.debug(f"FAILED: {ip}:{port} as {res[2]} - {res[1]}")

    return successful_tests_info


async def process_scan_results(scan_data, config_main):
    if not scan_data or 'scan' not in scan_data or not scan_data.get('scan'):
        logging.info("Scan returned no data, an error occurred, or no hosts were found in the scan results.")
        return []

    open_ports_candidates = []
    for ip_addr, details in scan_data['scan'].items():
        if 'tcp' in details:
            for port_num_str in details['tcp'].keys():
                try:
                    port_num = int(port_num_str)
                    open_ports_candidates.append({'ip': ip_addr, 'port': port_num})
                except ValueError:
                    logging.warning(f"Could not parse port number: {port_num_str} for IP {ip_addr}")

    if not open_ports_candidates:
        logging.info("No open ports found by masscan to test, or ports could not be parsed.")
        return []

    logging.info(f"Found {len(open_ports_candidates)} open IP/port combinations. Starting proxy validation...")
    validation_tasks = [test_single_proxy_candidate(cand['ip'], cand['port'], config_main) for cand in open_ports_candidates]
    all_results = await asyncio.gather(*validation_tasks, return_exceptions=True)

    final_working_proxies = []
    for i, candidate in enumerate(open_ports_candidates):
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
            logging.error("Please install it manually: pip install aiohttp-socks")

    config = load_config()
    ip_range = config.get('scan', 'ip_range')
    scan_speed = config.get('scan', 'scan_speed')
    ports_str = config.get('scan', 'ports')
    ports_list = [int(p.strip()) for p in ports_str.split(',') if p.strip().isdigit()]
    masscan_custom_args = config.get('scan', 'masscan_args', fallback='')

    logging.info(f"Configuration loaded: IP Range: {ip_range}, Scan Speed: {scan_speed} pps, Ports: {ports_list}")

    scan_output = scan_ports(ip_range, ports_list, scan_speed, masscan_custom_args)

    working_proxies = await process_scan_results(scan_output, config)

    logging.info(f"\n--- Summary of Working Proxies ({len(working_proxies)}) ---")
    if working_proxies:
        working_proxies.sort(key=lambda p: (p['ip'], p['port'], p['protocol']))

        with open("results.txt", "w") as f:
            for proxy in working_proxies:
                logging.info(f"  SAVING: {proxy['ip']}:{proxy['port']} # {proxy['protocol']} (Time: {proxy['response_time_ms']:.2f}ms)")
                f.write(f"{proxy['ip']}:{proxy['port']} # {proxy['protocol']}\n")
        logging.info(f"Working proxies saved to results.txt (Total: {len(working_proxies)})")
    else:
        logging.info("No working proxies found after validation.")
        with open("results.txt", "w") as f:
            f.write("# No working proxies found during this scan.\n")
        logging.info("results.txt updated to reflect no working proxies found.")

if __name__ == '__main__':
    asyncio.run(amain())
