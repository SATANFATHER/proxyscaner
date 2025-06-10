import asyncio
import unittest
from unittest.mock import patch, MagicMock, AsyncMock

# Add project root to sys.path to allow importing proxy_tester
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Ensure proxy_tester can be imported, provide dummy if not found (e.g. during isolated test runs)
try:
    from proxy_tester import test_socks4_proxy, test_socks5_proxy, test_http_proxy, DEFAULT_TEST_URL, DEFAULT_TIMEOUT
except ImportError:
    # Create a dummy proxy_tester.py in the root if it's missing
    # This helps if tests are run in an environment where the main setup hasn't happened
    print("Warning: proxy_tester.py not found in parent directory, creating a dummy for test purposes.")
    if not os.path.exists(os.path.join(os.path.dirname(__file__), '..', 'proxy_tester.py')):
        with open(os.path.join(os.path.dirname(__file__), '..', 'proxy_tester.py'), "w") as f_dummy:
            f_dummy.write("""
import asyncio
# Dummy implementations for testing imports
DEFAULT_TEST_URL = "http://dummy.url"
DEFAULT_TIMEOUT = 1
async def test_socks4_proxy(ip, port, url, timeout): return (False, "Dummy: Not Implemented", "SOCKS4")
async def test_socks5_proxy(ip, port, url, timeout): return (False, "Dummy: Not Implemented", "SOCKS5")
async def test_http_proxy(ip, port, url, timeout, is_https_tunnel=False): return (False, "Dummy: Not Implemented", "HTTP/S")
""")
    from proxy_tester import test_socks4_proxy, test_socks5_proxy, test_http_proxy, DEFAULT_TEST_URL, DEFAULT_TIMEOUT


# Mock aiohttp_socks if not installed, as it's a dependency for proxy_tester
try:
    import aiohttp_socks
except ImportError:
    sys.modules['aiohttp_socks'] = MagicMock()
    sys.modules['aiohttp_socks'].ProxyConnector = MagicMock()
    sys.modules['aiohttp_socks'].ProxyConnector.from_url = MagicMock(return_value=AsyncMock())
    print("Warning: aiohttp-socks not found, using a mock. SOCKS tests might not be fully representative.")


class TestProxyTester(unittest.IsolatedAsyncioTestCase):

    async def test_http_proxy_success(self):
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value='{"origin": "1.2.3.4"}') # Expected proxy IP

        # The context manager for session.get
        async def mock_get_context_manager(*args, **kwargs):
            return mock_response

        mock_session_instance = AsyncMock()
        # session.get() returns an async context manager
        mock_session_instance.get = MagicMock(return_value=AsyncMock(__aenter__=mock_get_context_manager, __aexit__=AsyncMock(return_value=False)))


        # aiohttp.ClientSession() itself is a context manager
        async def mock_session_cm_aenter(*args, **kwargs):
            return mock_session_instance

        mock_clientsession_cm = AsyncMock(__aenter__=mock_session_cm_aenter, __aexit__=AsyncMock(return_value=False))

        with patch('aiohttp.ClientSession', return_value=mock_clientsession_cm) as mock_aio_clientsession:
            is_success, rtt_ms, proto = await test_http_proxy('1.2.3.4', 8080, test_url='http://httpbin.org/ip', timeout_seconds=1)

            self.assertTrue(is_success)
            self.assertEqual(proto, "HTTP")
            self.assertIsInstance(rtt_ms, float)
            # Check that ClientSession was called (it's a context manager, so its __aenter__ is what we see first)
            mock_aio_clientsession.assert_called_once()
            # Check that session.get was called on the instance
            mock_session_instance.get.assert_called_once_with('http://httpbin.org/ip', proxy='http://1.2.3.4:8080', timeout=1)

    async def test_http_proxy_failure_status(self):
        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.text = AsyncMock(return_value='Error')
        async def mock_get_context_manager(*args, **kwargs): return mock_response
        mock_session_instance = AsyncMock()
        mock_session_instance.get = MagicMock(return_value=AsyncMock(__aenter__=mock_get_context_manager, __aexit__=AsyncMock(return_value=False)))
        async def mock_session_cm_aenter(*args, **kwargs): return mock_session_instance
        mock_clientsession_cm = AsyncMock(__aenter__=mock_session_cm_aenter, __aexit__=AsyncMock(return_value=False))

        with patch('aiohttp.ClientSession', return_value=mock_clientsession_cm):
            is_success, info, proto = await test_http_proxy('1.2.3.4', 8080, timeout_seconds=1)

            self.assertFalse(is_success)
            self.assertEqual(proto, "HTTP")
            self.assertIn("failed with status 500", info)

    async def test_http_proxy_timeout(self):
        # Mock session.get() to raise asyncio.TimeoutError
        mock_session_instance = AsyncMock()
        mock_session_instance.get = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(side_effect=asyncio.TimeoutError("Test timeout")),
            __aexit__=AsyncMock(return_value=False) # Ensure __aexit__ can be called
        ))
        async def mock_session_cm_aenter(*args, **kwargs): return mock_session_instance
        mock_clientsession_cm = AsyncMock(__aenter__=mock_session_cm_aenter, __aexit__=AsyncMock(return_value=False))

        with patch('aiohttp.ClientSession', return_value=mock_clientsession_cm):
            is_success, info, proto = await test_http_proxy('1.2.3.4', 8080, timeout_seconds=1)

            self.assertFalse(is_success)
            self.assertEqual(proto, "HTTP") # or specific protocol being tested
            self.assertIn("connection timed out", info)

    async def test_socks5_proxy_success(self):
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value='{"origin": "1.2.3.4"}')
        async def mock_get_context_manager(*args, **kwargs): return mock_response

        mock_session_instance = AsyncMock()
        mock_session_instance.get = MagicMock(return_value=AsyncMock(__aenter__=mock_get_context_manager, __aexit__=AsyncMock(return_value=False)))

        async def mock_session_cm_aenter(*args, **kwargs): return mock_session_instance
        mock_clientsession_cm = AsyncMock(__aenter__=mock_session_cm_aenter, __aexit__=AsyncMock(return_value=False))

        # Mock for ProxyConnector.from_url(). This returns a connector instance.
        mock_connector_instance = AsyncMock()
        mock_connector_instance.close = AsyncMock() # Ensure connector can be closed

        with patch('aiohttp_socks.ProxyConnector.from_url', return_value=mock_connector_instance) as mock_from_url, \
             patch('aiohttp.ClientSession', return_value=mock_clientsession_cm) as mock_aio_session_constructor:

            is_success, rtt_ms, proto = await test_socks5_proxy('1.2.3.4', 1080, test_url='http://httpbin.org/ip', timeout_seconds=1)

            self.assertTrue(is_success)
            self.assertEqual(proto, "SOCKS5")
            self.assertIsInstance(rtt_ms, float)
            mock_from_url.assert_called_once_with('socks5://1.2.3.4:1080')
            # ClientSession constructor is called with the connector
            mock_aio_session_constructor.assert_called_once_with(connector=mock_connector_instance)
            # get is called on the session instance
            mock_session_instance.get.assert_called_once_with('http://httpbin.org/ip', timeout=1)
            mock_connector_instance.close.assert_called_once()


    async def test_socks4_proxy_client_error(self):
        # Mock session.get() to raise a generic ClientError
        from aiohttp import ClientError # Ensure this is imported if not already

        mock_session_instance = AsyncMock()
        mock_session_instance.get = MagicMock(return_value=AsyncMock(
             __aenter__=AsyncMock(side_effect=ClientError("Test ClientError")),
             __aexit__=AsyncMock(return_value=False)
        ))

        async def mock_session_cm_aenter(*args, **kwargs): return mock_session_instance
        mock_clientsession_cm = AsyncMock(__aenter__=mock_session_cm_aenter, __aexit__=AsyncMock(return_value=False))

        mock_connector_instance = AsyncMock()
        mock_connector_instance.close = AsyncMock()

        with patch('aiohttp_socks.ProxyConnector.from_url', return_value=mock_connector_instance) as mock_from_url, \
             patch('aiohttp.ClientSession', return_value=mock_clientsession_cm) as mock_aio_session_constructor:

            is_success, info, proto = await test_socks4_proxy('1.2.3.4', 1080, timeout_seconds=1)

            self.assertFalse(is_success)
            self.assertEqual(proto, "SOCKS4")
            self.assertIn("SOCKS4 ClientError: Test ClientError", info)
            mock_connector_instance.close.assert_called_once()


if __name__ == '__main__':
    # Ensure aiohttp-socks is installed for the test environment, or mock it.
    # The mock above handles it if not installed.
    # If proxy_tester.py itself tries to install it, that might interfere in a test context.
    # For tests, it's better to assume dependencies are met or mocked.

    # To run these tests: python -m unittest tests.test_proxy_tester
    unittest.main()
