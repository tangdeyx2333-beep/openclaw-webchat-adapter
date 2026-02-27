import unittest
from openclaw_webchat_adapter.ws_adapter import DeviceIdentity, OpenClawChatWsAdapter
from openclaw_webchat_adapter.config import AdapterSettings
from cryptography.hazmat.primitives.asymmetric import ed25519
import json
from unittest.mock import MagicMock, patch

class TestDeviceSigning(unittest.TestCase):
    def test_device_identity_generation(self):
        device = DeviceIdentity.generate()
        self.assertIsInstance(device.private_key, ed25519.Ed25519PrivateKey)
        self.assertTrue(len(device.device_id) > 0)
        self.assertTrue(len(device.public_key_b64) > 0)

    def test_device_signing_payload(self):
        device = DeviceIdentity.generate()
        payload = "test_payload"
        signature = device.sign_payload(payload)
        self.assertTrue(len(signature) > 0)
        
        # Verify signature using public key
        import base64
        sig_bytes = base64.urlsafe_b64decode(signature + "===")
        device.private_key.public_key().verify(sig_bytes, payload.encode("utf-8"))

    @patch("openclaw_webchat_adapter.ws_adapter.OpenClawChatWsAdapter._send")
    def test_send_connect_with_signing(self, mock_send):
        settings = AdapterSettings(
            token="test-token",
            client_id="test-client",
            role="operator",
            scopes_csv="scope1,scope2"
        )
        device = DeviceIdentity.generate()
        adapter = OpenClawChatWsAdapter(settings, device=device)
        
        # Mock WebSocket to bypass early return
        adapter._ws = MagicMock()
        
        # Manually trigger _send_connect
        adapter._connect_req_id = "test-req-id"
        adapter._send_connect()
        
        # Check if _send was called with correct frame
        self.assertTrue(mock_send.called)
        frame = mock_send.call_args[0][0]
        
        self.assertEqual(frame["method"], "connect")
        params = frame["params"]
        self.assertIn("device", params)
        
        dev_params = params["device"]
        self.assertEqual(dev_params["id"], device.device_id)
        self.assertEqual(dev_params["publicKey"], device.public_key_b64)
        self.assertIn("signature", dev_params)
        self.assertIn("signedAt", dev_params)
        self.assertEqual(dev_params["nonce"], "") # No nonce yet

    def test_device_identity_persistence(self):
        import os
        import tempfile
        
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = tmp.name
        
        try:
            device = DeviceIdentity.generate()
            device.save_to_file(tmp_path)
            
            # Load and verify
            loaded = DeviceIdentity.load_from_file(tmp_path)
            self.assertIsNotNone(loaded)
            self.assertEqual(device.device_id, loaded.device_id)
            self.assertEqual(device.public_key_b64, loaded.public_key_b64)
            
            # Test sign with loaded key
            payload = "persistence_test"
            sig1 = device.sign_payload(payload)
            sig2 = loaded.sign_payload(payload)
            self.assertEqual(sig1, sig2)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    @patch("openclaw_webchat_adapter.ws_adapter.OpenClawChatWsAdapter.create_connected")
    def test_create_connected_from_env_auto_persistence(self, mock_create_connected):
        import os
        import tempfile
        from openclaw_webchat_adapter.ws_adapter import OpenClawChatWsAdapter
        
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = tmp.name
        
        try:
            # Case 1: File doesn't exist, should generate and save
            if os.path.exists(tmp_path): os.remove(tmp_path)
            
            with patch.dict(os.environ, {"OPENCLAW_DEVICE_KEY_FILE": tmp_path}):
                OpenClawChatWsAdapter.create_connected_from_env()
            
            self.assertTrue(os.path.exists(tmp_path))
            device1 = DeviceIdentity.load_from_file(tmp_path)
            self.assertIsNotNone(device1)
            
            # Case 2: File exists, should load
            with patch.dict(os.environ, {"OPENCLAW_DEVICE_KEY_FILE": tmp_path}):
                OpenClawChatWsAdapter.create_connected_from_env()
            
            device2 = DeviceIdentity.load_from_file(tmp_path)
            self.assertEqual(device1.device_id, device2.device_id)
            
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

if __name__ == "__main__":
    unittest.main()
