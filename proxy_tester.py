import asyncio
import aiohttp
import requests # Will be replaced/supplemented by aiohttp
import time

# Placeholder for a common test URL, can be overridden by config
DEFAULT_TEST_URL = "http://httpbin.org/ip" # Using httpbin for IP checking
DEFAULT_TIMEOUT = 5 # seconds

# Helper to get aiohttp session with appropriate connector
def get_aiohttp_session(connector=None):
    return aiohttp.ClientSession(connector=connector)

async def test_socks4_proxy(proxy_ip, proxy_port, test_url=DEFAULT_TEST_URL, timeout_seconds=DEFAULT_TIMEOUT):
    """
    Tests a SOCKS4 proxy using aiohttp and a SOCKS connector.
    Returns: (True, response_time_ms, "SOCKS4") if successful, (False, error_message, "SOCKS4") otherwise.
    """
    from aiohttp_socks import ProxyConnector
    connector = ProxyConnector.from_url(f'socks4://{proxy_ip}:{proxy_port}')
    start_time = time.perf_counter()
    try:
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get(test_url, timeout=timeout_seconds) as response:
                response_text = await response.text() # Ensure we read the body
                end_time = time.perf_counter()
                response_time_ms = (end_time - start_time) * 1000
                # Basic validation: status code and try to check if IP is proxy's IP (can be tricky)
                if response.status == 200:
                    # For httpbin.org/ip, the response is JSON like: {"origin": "PROXY_IP"}
                    # This check isn't foolproof as some proxies might be transparent or show local IP.
                    # A more robust check might involve comparing against the proxy_ip, but httpbin shows egress IP.
                    if proxy_ip in response_text: # Simplified check
                         return (True, response_time_ms, "SOCKS4")
                    # If IP check is not reliable, just accept 200 OK for now
                    return (True, response_time_ms, "SOCKS4")
                else:
                    return (False, f"SOCKS4 connection failed with status {response.status}", "SOCKS4")
    except asyncio.TimeoutError:
        return (False, "SOCKS4 connection timed out", "SOCKS4")
    except aiohttp.ClientError as e:
        return (False, f"SOCKS4 ClientError: {str(e)}", "SOCKS4")
    except Exception as e:
        return (False, f"SOCKS4 unexpected error: {str(e)}", "SOCKS4")
    finally:
        if 'connector' in locals() and connector: # Ensure connector is defined
             await connector.close()


async def test_socks5_proxy(proxy_ip, proxy_port, test_url=DEFAULT_TEST_URL, timeout_seconds=DEFAULT_TIMEOUT):
    """
    Tests a SOCKS5 proxy using aiohttp and a SOCKS connector.
    Returns: (True, response_time_ms, "SOCKS5") if successful, (False, error_message, "SOCKS5") otherwise.
    """
    from aiohttp_socks import ProxyConnector
    connector = ProxyConnector.from_url(f'socks5://{proxy_ip}:{proxy_port}')
    start_time = time.perf_counter()
    try:
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get(test_url, timeout=timeout_seconds) as response:
                response_text = await response.text()
                end_time = time.perf_counter()
                response_time_ms = (end_time - start_time) * 1000
                if response.status == 200:
                    if proxy_ip in response_text: # Simplified check
                        return (True, response_time_ms, "SOCKS5")
                    return (True, response_time_ms, "SOCKS5") # Accept 200 OK
                else:
                    return (False, f"SOCKS5 connection failed with status {response.status}", "SOCKS5")
    except asyncio.TimeoutError:
        return (False, "SOCKS5 connection timed out", "SOCKS5")
    except aiohttp.ClientError as e:
        return (False, f"SOCKS5 ClientError: {str(e)}", "SOCKS5")
    except Exception as e:
        return (False, f"SOCKS5 unexpected error: {str(e)}", "SOCKS5")
    finally:
        if 'connector' in locals() and connector: # Ensure connector is defined
            await connector.close()


async def test_http_proxy(proxy_ip, proxy_port, test_url=DEFAULT_TEST_URL, timeout_seconds=DEFAULT_TIMEOUT, is_https_tunnel=False):
    """
    Tests an HTTP proxy. If is_https_tunnel is True, it tests ability to tunnel HTTPS traffic.
    Returns: (True, response_time_ms, protocol) if successful, (False, error_message, protocol) otherwise.
    Protocol is "HTTP" or "HTTPS (Tunneled)".
    """
    # The proxy_url for aiohttp is the full URL to the proxy itself.
    http_proxy_url = f"http://{proxy_ip}:{proxy_port}"
    protocol_tested = "HTTPS (Tunneled)" if is_https_tunnel else "HTTP"
    # The actual test_url (e.g., http://httpbin.org/ip or https://api.ipify.org) is what we fetch *through* the proxy.
    # If is_https_tunnel is true, we should ideally test with an HTTPS test_url.
    # For simplicity, we use the same test_url but rely on the proxy handling the CONNECT method for HTTPS.

    start_time = time.perf_counter()
    try:
        # For HTTPS tunnel, aiohttp handles the CONNECT request transparently if proxy URL is http and target URL is https
        target_url_to_fetch = test_url
        if is_https_tunnel and not test_url.startswith("https://"):
            # If we're testing an HTTPS tunnel, ensure the target is an HTTPS site for a proper test.
            # This is a fallback, ideally the caller provides an appropriate test_url.
            target_url_to_fetch = "https://api.ipify.org"


        async with aiohttp.ClientSession() as session: # No special connector for basic HTTP proxy
            async with session.get(target_url_to_fetch, proxy=http_proxy_url, timeout=timeout_seconds) as response:
                response_text = await response.text()
                end_time = time.perf_counter()
                response_time_ms = (end_time - start_time) * 1000
                if response.status == 200:
                    # Basic validation for httpbin.org/ip or api.ipify.org (plain IP)
                    if proxy_ip in response_text: # Simplified check, might not always work
                         return (True, response_time_ms, protocol_tested)
                    # If IP check is not reliable, just accept 200 OK
                    return (True, response_time_ms, protocol_tested)
                else:
                    return (False, f"{protocol_tested} connection failed with status {response.status}", protocol_tested)
    except asyncio.TimeoutError:
        return (False, f"{protocol_tested} connection timed out", protocol_tested)
    except aiohttp.ClientProxyConnectionError as e:
        return (False, f"{protocol_tested} Proxy Connection Error: {e}", protocol_tested)
    except aiohttp.ClientError as e:
        return (False, f"{protocol_tested} ClientError: {str(e)}", protocol_tested)
    except Exception as e:
        return (False, f"{protocol_tested} unexpected error: {str(e)}", protocol_tested)

# Example of how these might be called (for testing the file itself)
if __name__ == '__main__':
    # For these tests to run, you'd need aiohttp-socks installed
    # And actual proxy servers running on localhost for them to connect to.
    # This is more of a structural check.

    # Ensure aiohttp-socks is available for SOCKS tests
    try:
        from aiohttp_socks import ProxyConnector
    except ImportError:
        print("Please install aiohttp-socks to run SOCKS proxy tests: pip install aiohttp-socks")
        # You might choose to exit or skip SOCKS tests if not installed
        # For now, the functions will fail gracefully if called without it.

    async def main_test_runner():
        # These will likely fail unless proxies are running on these ports
        # and aiohttp-socks is installed.
        # The purpose here is to ensure the functions are callable and run without syntax errors.
        print("Running proxy_tester.py self-tests (requires aiohttp-socks and potentially live local proxies)...")

        dummy_ip, dummy_port = "127.0.0.1", 1080 # Example SOCKS port

        print("\n--- Testing SOCKS4 (dummy) ---")
        res_s4 = await test_socks4_proxy(dummy_ip, dummy_port, test_url="http://httpbin.org/ip")
        print(f"SOCKS4 -> Success: {res_s4[0]}, Info: {res_s4[1]}, Type: {res_s4[2]}, Time: {res_s4[1] if res_s4[0] else 'N/A'}")

        print("\n--- Testing SOCKS5 (dummy) ---")
        res_s5 = await test_socks5_proxy(dummy_ip, dummy_port, test_url="http://httpbin.org/ip")
        print(f"SOCKS5 -> Success: {res_s5[0]}, Info: {res_s5[1]}, Type: {res_s5[2]}, Time: {res_s5[1] if res_s5[0] else 'N/A'}")

        dummy_http_port = 8080 # Example HTTP proxy port
        print("\n--- Testing HTTP (dummy) ---")
        res_http = await test_http_proxy(dummy_ip, dummy_http_port, test_url="http://httpbin.org/ip")
        print(f"HTTP -> Success: {res_http[0]}, Info: {res_http[1]}, Type: {res_http[2]}, Time: {res_http[1] if res_http[0] else 'N/A'}")

        print("\n--- Testing HTTPS (Tunneled via HTTP proxy) (dummy) ---")
        # Using a different test URL for HTTPS to ensure it's actually an HTTPS site
        res_https = await test_http_proxy(dummy_ip, dummy_http_port, test_url="https://api.ipify.org", is_https_tunnel=True)
        print(f"HTTPS (Tunneled) -> Success: {res_https[0]}, Info: {res_https[1]}, Type: {res_https[2]}, Time: {res_https[1] if res_https[0] else 'N/A'}")

        print("\nSelf-tests complete. Failures are expected if no proxies are running on localhost or aiohttp-socks is not installed.")

    # Install aiohttp-socks for the SOCKS tests
    # This should ideally be in requirements.txt and installed earlier,
    # but for the subtask, let's ensure it's available.
    import os
    os.system("pip install aiohttp-socks") # Make sure it's available for the test run

    asyncio.run(main_test_runner())
