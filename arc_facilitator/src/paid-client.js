// Explicit --pay only. Never run by tests. One 0.10 USDC authorization,
// no funding transfers and no automatic paid retry after ambiguity.
import { privateKeyToAccount } from 'viem/accounts';
import { ExactEvmScheme } from '@x402/evm/exact/client';
import { USDC } from './probe.js';
process.on('uncaughtException', e => { const reason = /^[a-z_]+$/.test(e.message) ? e.message : 'http_or_sdk_error'; console.error('Paid client failed: ' + reason + '. Do not retry a paid request until settlement is reconciled.'); process.exit(1); });
const url = 'https://hexdrive.tech/api/audit/paid';
const request = { url: 'https://example.com', is_public: false };
const headers = { 'content-type': 'application/json' };
const first = await fetch(url, { method: 'POST', redirect: 'error', headers, body: JSON.stringify(request), signal: AbortSignal.timeout(30000) });
if (first.status !== 402) throw new Error('expected_402_before_signing');
const raw = first.headers.get('payment-required');
if (!raw || raw.length > 32768) throw new Error('invalid_payment_required');
const required = JSON.parse(Buffer.from(raw, 'base64').toString());
const network = process.env.ARC_CLIENT_NETWORK || 'eip155:5042';
if (!['eip155:5042', 'eip155:5042002'].includes(network)) throw new Error('unsupported_network');
const expectedRecipient = process.env.ARC_CLIENT_PAY_TO || '0x69a01903E635587C3e28DaAfF5DB82B369447e76';
if (required.x402Version !== 2 || (required.resource?.url && required.resource.url !== url)) throw new Error('unexpected_resource_or_version');
const r = required.accepts?.find(r => r.network === network && r.scheme === 'exact' && r.asset?.toLowerCase() === USDC.toLowerCase() && r.payTo?.toLowerCase() === expectedRecipient.toLowerCase() && r.amount === '100000' && r.extra?.name === 'USDC' && r.extra?.version === '2' && (!r.extra?.assetTransferMethod || r.extra.assetTransferMethod === 'eip3009') && Number.isInteger(r.maxTimeoutSeconds) && r.maxTimeoutSeconds >= 10 && r.maxTimeoutSeconds <= 300);
if (!r) throw new Error('no_approved_exact_arc_offer');
if (required.extensions && Object.keys(required.extensions).length) throw new Error('extensions_not_approved');
console.log(JSON.stringify({ target: url, auditUrl: request.url, isPublic: false, network, asset: r.asset, amount: r.amount, payTo: r.payTo, mode: process.argv.includes('--pay') ? 'single_paid_request' : 'quote_only' }));
if (process.argv.includes('--pay')) {
  const key = process.env.ARC_CLIENT_PRIVATE_KEY;
  if (!/^0x[0-9a-fA-F]{64}$/.test(key || '')) throw new Error('dedicated_payer_key_required');
  const account = privateKeyToAccount(key);
  const signed = await new ExactEvmScheme(account).createPaymentPayload(2, r);
  const payload = { x402Version: 2, accepted: r, resource: required.resource, payload: signed.payload };
  const paid = await fetch(url, { method: 'POST', redirect: 'error', headers: { ...headers, 'payment-signature': Buffer.from(JSON.stringify(payload)).toString('base64') }, body: JSON.stringify(request), signal: AbortSignal.timeout(180000) });
  const settlement = paid.headers.get('payment-response');
  const body = await paid.json();
  console.log(JSON.stringify({ status: paid.status, settlement: settlement ? JSON.parse(Buffer.from(settlement, 'base64').toString()) : null, result: body }));
  if (!paid.ok) process.exitCode = 1;
}
