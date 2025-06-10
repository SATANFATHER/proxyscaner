# Global Proxy Scanner

This project is a Python-based proxy scanner that performs the following tasks:

1.  Scans IP ranges globally using masscan-style port scanning.
2.  Tests for SOCKS4, SOCKS5, HTTP, and HTTPS proxy protocols.
3.  Targets common proxy ports (configurable, defaults include 1080, 3128, 8080, 8888, 9999, and others).
4.  Validates each discovered proxy by:
    *   Attempting a test connection to a verification URL.
    *   Verifying successful data transfer (implied by a successful GET request).
    *   Checking response times (logged, and can be used for filtering if extended).
    *   Confirming protocol compatibility.

## Output

*   Working proxies are saved to `results.txt`.
*   Format: `ip:port # protocol_type` on each line.
*   Non-responsive or failed proxies are skipped.

## Requirements

*   Python 3.7+
*   `masscan` installed and available in your system's PATH.
*   Python libraries listed in `requirements.txt`.

## Setup

1.  **Clone the repository (if applicable) or ensure all files are in the same directory:**
    *   `main.py`
    *   `proxy_tester.py`
    *   `config.ini`
    *   `requirements.txt`

2.  **Install `masscan`:**
    *   On Debian/Ubuntu: `sudo apt-get update && sudo apt-get install masscan`
    *   On macOS (using Homebrew): `brew install masscan`
    *   From source: [masscan GitHub](https://github.com/robertdavidgraham/masscan)

3.  **Install Python dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
    *(Note: `aiohttp-socks` is a key dependency for SOCKS proxy testing. The script `main.py` and `proxy_tester.py` attempt to install it if missing, but manual installation is recommended.)*

## Configuration

Edit the `config.ini` file to set your desired scanning parameters:

```ini
[scan]
ip_range = 0.0.0.0/0       ; IP range to scan (e.g., 192.168.0.0/16, or a specific IP like 1.2.3.4)
scan_speed = 10000         ; Packets per second for masscan (be careful with high values)
timeout = 5                ; Timeout in seconds for each proxy test connection
ports = 1080,3128,8080,8888,9999,80,443,8000,8081 ; Comma-separated list of ports to scan
test_url = http://httpbin.org/ip ; URL used to test HTTP/SOCKS proxies (should return client's IP)
https_test_url = https://api.ipify.org ; URL used to test HTTPS tunnel capability (should be an HTTPS site)
masscan_args =             ; Optional: Additional arguments for masscan (e.g., --exclude 255.255.255.255)
```

**Important:** Scanning `0.0.0.0/0` will scan the entire internet. This is generally not recommended, illegal in some contexts, and will take an extremely long time. Use more specific IP ranges.

## Running the Scanner

Execute the main script from your terminal:

```bash
python main.py
```

The script will:
1.  Load the configuration.
2.  Run `masscan` to find open ports.
3.  Test the identified IP:port combinations for SOCKS4, SOCKS5, HTTP, and HTTPS proxy protocols.
4.  Save working proxies to `results.txt`.
5.  Log progress and results to the console.

## Unit Tests

Basic unit tests for the `proxy_tester.py` module are located in the `tests/` directory. To run them:

```bash
python -m unittest tests.test_proxy_tester
```
or
```bash
python tests/test_proxy_tester.py
```

EOF
