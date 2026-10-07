// Read-only live RPC/HTTP/SDK smoke. Ephemeral, unfunded accounts only.
import { generatePrivateKey, privateKeyToAccount } from 'viem/accounts';
import { ExactEvmScheme as ClientScheme } from '@x402/evm/exact/client';
import { loadConfig } from './config.js';
import { Ledger } from './ledger.js';
import { createService } from './service.js';
import { httpServer } from './server.js';
import { USDC } from './probe.js';
process.on('uncaughtException', () => { console.error('Read-only smoke failed: check RPC availability/rate limits and startup validation.'); process.exit(1); });
const payer = privateKeyToAccount(generatePrivateKey());
const recipient = '0x69a01903E635587C3e28DaAfF5DB82B369447e76';
const config = loadConfig({ ARC_FACILITATOR_PRIVATE_KEY: generatePrivateKey(), ARC_ALLOWED_PAY_TO: recipient, ARC_NETWORKS: 'eip155:5042,eip155:5042002', ARC_FACILITATOR_API_TOKEN: 'ephemeral-test-token-'.repeat(3), ARC_MAINNET_RPC_URL: process.env.ARC_MAINNET_RPC_URL, ARC_TESTNET_RPC_URL: process.env.ARC_TESTNET_RPC_URL });
const ledger = new Ledger(':memory:');
const service = await createService(config, ledger), server = httpServer(service, config.token);
await new Promise(r => server.listen(0, '127.0.0.1', r));
const url = 'http://127.0.0.1:' + server.address().port;
try {
  console.log(JSON.stringify({ supported: await (await fetch(url + '/supported')).json() }));
  for (const network of config.networks) {
    const r = { scheme: 'exact', network, asset: USDC, amount: '100000', payTo: recipient, maxTimeoutSeconds: 300, extra: { name: 'USDC', version: '2' } };
    const signed = await new ClientScheme(payer).createPaymentPayload(2, r);
    const b = { x402Version: 2, paymentPayload: { ...signed, accepted: r }, paymentRequirements: r };
    const request = async path => (await fetch(url + path, { method: 'POST', headers: { authorization: 'Bearer ' + config.token, 'content-type': 'application/json' }, body: JSON.stringify(b) })).json();
    const verified = await request('/verify');
    if (verified.isValid) throw new Error('unexpected_unfunded_verify_success');
    const settled = await request('/settle');
    if (settled.success || settled.errorReason !== 'settlement_disabled') throw new Error('unexpected_settle_result');
    b.paymentPayload.payload.signature = '0x' + '11'.repeat(65);
    const invalid = await request('/verify');
    if (invalid.isValid) throw new Error('invalid_signature_accepted');
    console.log(JSON.stringify({ network, validSignatureUnfunded: verified, invalidSignature: invalid, disabledSettle: settled, transactionsSubmitted: 0 }));
  }
} finally { await new Promise(r => server.close(r)); ledger.close(); }
