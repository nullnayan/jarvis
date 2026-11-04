"""Exercise real gateway authentication with provider and background jobs isolated."""
import asyncio
import importlib.util
import logging
import os
from pathlib import Path
import secrets
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from twilio.request_validator import RequestValidator
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidHandshake

import cloud.hub as hub_module
from cloud import twilio_handler
from logger import SecretRedactionFilter
from server import ws_server
from security.transport import require_secure_gateway

ROOT = Path(__file__).resolve().parents[2]


class CloudGatewaySecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Load the real routing layer without invoking providers, scrapers or a database.
        monitor = types.ModuleType('cloud.deal_monitor')
        monitor.DealMonitor = lambda *args: types.SimpleNamespace(
            run_forever=AsyncMock(), stop=lambda: None, trigger_immediate_run=lambda: None)
        database = types.ModuleType('cloud.deal_db')
        database.DealDB = lambda: types.SimpleNamespace(
            get_global_toggle=AsyncMock(return_value=False), get_active_watches=AsyncMock(return_value=[]))
        brain = types.ModuleType('cloud.cloud_brain')
        brain.cloud_brain = types.SimpleNamespace(call_state=types.SimpleNamespace(active=False, mode='off'))
        name='isolated_gateway_server'
        spec=importlib.util.spec_from_file_location(name,ROOT/'backend/cloud/server.py')
        cls.server=importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules,{name:cls.server,'cloud.deal_monitor':monitor,
                                    'cloud.deal_db':database,'cloud.cloud_brain':brain}):
            spec.loader.exec_module(cls.server)

    def setUp(self):
        self.token=secrets.token_hex(32)
        self.server_token=patch.object(self.server,'JARVIS_AUTH_TOKEN',self.token)
        self.hub_token=patch.object(hub_module,'JARVIS_AUTH_TOKEN',self.token)
        self.server_token.start();self.hub_token.start()
        self.client=TestClient(self.server.app)

    def tearDown(self):
        self.client.close();self.hub_token.stop();self.server_token.stop()

    def test_private_routes_reject_missing_and_invalid_tokens(self):
        routes=[('GET','/status'),('GET','/api/call-log'),('DELETE','/api/call-log'),
                ('GET','/api/urgent-decision'),('GET','/api/deal-status'),
                ('GET','/api/test-deal-alert'),('POST','/api/test-deal-alert')]
        for method,path in routes:
            for params in [{},{'token':'incorrect'},{'token':'é-invalid'}]:
                with self.subTest(method=method,path=path,params=params):
                    self.assertEqual(self.client.request(method,path,params=params).status_code,401)

    def test_status_accepts_explicit_current_token(self):
        response=self.client.get('/status',params={'token':self.token})
        self.assertEqual(response.status_code,200)

    def test_startup_refuses_unconfigured_authentication(self):
        with patch.object(self.server,'JARVIS_AUTH_TOKEN',''):
            with self.assertRaises(RuntimeError):
                with TestClient(self.server.app):pass

    def test_health_discloses_no_call_state(self):
        data=self.client.get('/health').json()
        self.assertEqual(data['status'],'online')
        self.assertNotIn('sleep_mode',data)
        self.assertNotIn('call_mode',data)

    def test_unknown_websocket_roles_are_rejected(self):
        from starlette.websockets import WebSocketDisconnect
        with self.assertRaises(WebSocketDisconnect):
            with self.client.websocket_connect('/ws/administrator',params={'token':self.token}):pass


class TwilioSignatureTests(unittest.TestCase):
    def setUp(self):
        self.secret=secrets.token_hex(32)
        self.base='https://calls.example.com'
        self.token_patch=patch.object(twilio_handler,'TWILIO_AUTH_TOKEN',self.secret)
        self.base_patch=patch.object(twilio_handler,'TWILIO_WEBHOOK_BASE',self.base)
        self.token_patch.start();self.base_patch.start()
        app=FastAPI()
        @app.post('/webhook',dependencies=[Depends(twilio_handler.require_twilio_signature)])
        async def webhook():return {'ok':True}
        self.client=TestClient(app)

    def tearDown(self):
        self.client.close();self.base_patch.stop();self.token_patch.stop()

    def test_unsigned_and_forged_webhooks_are_rejected(self):
        for signature in ['', 'forged']:
            self.assertEqual(self.client.post('/webhook',data={'CallSid':'example'},
                             headers={'X-Twilio-Signature':signature}).status_code,403)

    def test_valid_signature_uses_configured_external_url(self):
        data={'CallSid':'example'}
        signature=RequestValidator(self.secret).compute_signature(self.base+'/webhook',data)
        response=self.client.post('/webhook',data=data,headers={'X-Twilio-Signature':signature,
                                                               'Host':'untrusted.invalid'})
        self.assertEqual(response.status_code,200)

    def test_modified_payload_is_rejected(self):
        signature=RequestValidator(self.secret).compute_signature(self.base+'/webhook',{'CallSid':'original'})
        self.assertEqual(self.client.post('/webhook',data={'CallSid':'changed'},
                         headers={'X-Twilio-Signature':signature}).status_code,403)


class DesktopSocketSecurityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.token=secrets.token_hex(32)
        self.patches=[patch.object(ws_server,'WS_AUTH_TOKEN',self.token),
                      patch.object(ws_server,'WS_HOST','127.0.0.1'),patch.object(ws_server,'WS_PORT',0)]
        for item in self.patches:item.start()
        self.server=ws_server.WebSocketServer()
        await self.server.start()
        self.url=f"ws://127.0.0.1:{self.server.server.sockets[0].getsockname()[1]}"

    async def asyncTearDown(self):
        await self.server.stop()
        for item in reversed(self.patches):item.stop()

    async def test_missing_and_invalid_credentials_cannot_dispatch(self):
        handled=[];self.server.on_message(handled.append)
        for headers in [{},{'Authorization':'Bearer wrong'}]:
            async with connect(self.url,additional_headers=headers) as socket:
                with self.assertRaises(ConnectionClosed):await socket.recv()
        self.assertEqual(handled,[])

    async def test_browser_origin_is_blocked_even_with_valid_token(self):
        with self.assertRaises(InvalidHandshake):
            async with connect(self.url,origin='https://untrusted.invalid',
                               additional_headers={'Authorization':'Bearer '+self.token}):pass

    async def test_authenticated_desktop_can_dispatch(self):
        event=asyncio.Event()
        self.server.on_message(lambda message:event.set())
        async with connect(self.url,additional_headers={'Authorization':'Bearer '+self.token}) as socket:
            await socket.send('{"type":"command","value":"hello"}')
            await asyncio.wait_for(event.wait(),2)


class LoggingSecurityTests(unittest.TestCase):
    def test_environment_secret_and_url_credentials_are_redacted(self):
        value=secrets.token_hex(32)
        record=logging.LogRecord('test',logging.ERROR,'',0,'failed %s https://example.com/?token=%s',
                                 (value,value),None)
        with patch.dict(os.environ,{'JARVIS_AUTH_TOKEN':value}):
            SecretRedactionFilter().filter(record)
        self.assertNotIn(value,record.getMessage())
        self.assertIn('[REDACTED]',record.getMessage())


class GatewayTransportTests(unittest.TestCase):
    def test_remote_plaintext_and_embedded_credentials_are_rejected(self):
        for url in ['http://gateway.example.com','ws://192.168.1.5:8765','https://user:password@example.com']:
            with self.subTest(url=url),self.assertRaises(ValueError):require_secure_gateway(url)

    def test_tls_and_local_loopback_are_supported(self):
        for url in ['https://gateway.example.com','wss://gateway.example.com/ws/pc','ws://127.0.0.1:8765','http://localhost:8765']:
            self.assertEqual(require_secure_gateway(url),url)


if __name__=='__main__':unittest.main()
