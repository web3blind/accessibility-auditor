import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { AsyncLocalStorage } from 'node:async_hooks';
import { verifyTypedData, parseAbi, encodeEventTopics, encodeAbiParameters } from 'viem';
import { generatePrivateKey, privateKeyToAccount } from 'viem/accounts';
import { x402Facilitator } from '@x402/core/facilitator';
import { ExactEvmScheme } from '@x402/evm/exact/facilitator';
import { ExactEvmScheme as ClientScheme } from '@x402/evm/exact/client';
import { USDC } from '../src/probe.js';
import { loadConfig } from '../src/config.js';
import { Ledger } from '../src/ledger.js';
import { validate, createHandlers, boundedWriter } from '../src/service.js';
import { httpServer } from '../src/server.js';
const account = privateKeyToAccount(generatePrivateKey());
const payTo = '0x69a01903E635587C3e28DaAfF5DB82B369447e76';
const config = loadConfig({ ARC_FACILITATOR_PRIVATE_KEY: generatePrivateKey(), ARC_ALLOWED_PAY_TO: payTo, ARC_FACILITATOR_API_TOKEN: 'test-only-token-'.repeat(3), ARC_NETWORKS: 'eip155:5042,eip155:5042002', ARC_SETTLEMENT_ENABLED: 'true' });
async function body(network = 'eip155:5042') {
  const r = { scheme: 'exact', network, asset: USDC, amount: '100000', payTo, maxTimeoutSeconds: 300, extra: { name: 'USDC', version: '2' } };
  const signed = await new ClientScheme(account).createPaymentPayload(2, r);
  return { x402Version: 2, paymentPayload: { ...signed, accepted: r }, paymentRequirements: r };
}
function fixture() {
  const ledger = new Ledger(':memory:'); let writes = 0, simulations = 0;
  const signer = { getAddresses: () => [account.address], getCode: async ({ address }) => address.toLowerCase() === USDC.toLowerCase() ? '0x6000' : '0x', verifyTypedData,
    readContract: async ({ functionName }) => { if (functionName === 'transferWithAuthorization') simulations++; return false; },
    simulateContract: async () => { simulations++; return {}; },
    writeContract: async () => { writes++; return '0x' + 'ab'.repeat(32); },
    waitForTransactionReceipt: async () => ({ status: 'success', logs: [{ address: USDC, topics: encodeEventTopics({ abi: parseAbi(['event Transfer(address indexed from,address indexed to,uint256 value)']), eventName: 'Transfer', args: { from: account.address, to: payTo } }), data: encodeAbiParameters([{ type: 'uint256' }], [100000n]) }] }),
  };
  const sdk = new x402Facilitator();
  for (const n of config.networks) sdk.register(n, new ExactEvmScheme(signer, { simulateInSettle: true }));
  const clients = Object.fromEntries(config.networks.map(n => [n, { getCode: async () => '0x' }]));
  return { ledger, sdk, service: createHandlers(config, ledger, sdk, clients), counts: () => ({ writes, simulations }) };
}
test('config defaults testnet, dedicated key/token/recipients required, networks bounded', () => {
  assert.throws(() => loadConfig({}), /recipient/);
  assert.throws(() => loadConfig({ ARC_NETWORKS: 'eip155:1' }), /unsupported_network/);
  assert.deepEqual(config.networks, ['eip155:5042', 'eip155:5042002']);
});
test('strict Arc USDC exact v2 recipient/amount/domain/payload boundaries', async () => {
  validate(await body(), config);
  for (const mutate of [b => b.x402Version = 1, b => b.paymentRequirements.network = 'eip155:1', b => b.paymentRequirements.asset = account.address,
    b => b.paymentRequirements.payTo = account.address, b => b.paymentRequirements.amount = '100001', b => b.paymentRequirements.extra.name = 'fake',
    b => b.paymentPayload.payload.signature += '00', b => b.paymentPayload.payload.permit2Authorization = {}, b => b.paymentPayload.accepted = {},
    b => b.paymentPayload.payload.authorization.validBefore = '999999999999']) {
    const b = await body(); mutate(b); assert.throws(() => validate(b, config));
  }
});
test('official SDK verifies real signatures on both Arc chain domains (mock simulation)', async () => {
  const f = fixture();
  for (const n of config.networks) assert.equal((await f.service.handle('verify', await body(n))).isValid, true);
  assert.equal(f.counts().writes, 0); assert.equal(f.counts().simulations, 2); f.ledger.close();
});
test('invalid signature cannot settle: actual official SDK verify and zero broadcasts', async () => {
  const f = fixture(), b = await body(); b.paymentPayload.payload.signature = '0x' + '11'.repeat(65);
  assert.equal((await f.service.handle('verify', b)).isValid, false);
  assert.equal((await f.service.handle('settle', b)).success, false);
  assert.equal(f.counts().writes, 0); f.ledger.close();
});
test('concurrent same authorization executes SDK settle once; replay denied', async () => {
  const f = fixture(), b = await body();
  const results = await Promise.all([f.service.handle('settle', b), f.service.handle('settle', b)]);
  assert.equal(f.counts().writes, 1);
  assert.ok(results.some(r => r.success === true && /^0x/.test(r.transaction)));
  assert.ok(results.some(r => r.errorReason === 'authorization_replay'));
  assert.equal((await f.service.handle('settle', b)).errorReason, 'authorization_replay'); f.ledger.close();
});
test('persistent ledger cross-connection serialization and daily reservation cap', () => {
  const l = new Ledger(':memory:'); l.claim('a'); assert.throws(() => l.claim('b'), /recovery/); l.finish('a', {}); l.claim('b');
  l.reserve(5n, 8n); assert.throws(() => l.reserve(5n, 8n), /budget/); assert.throws(() => l.claim('a'), /replay/); l.close();
});
test('durable cross-connection lock, replay and budget survive reopen', () => {
  const dir = mkdtempSync(join(process.env.TMPDIR || process.cwd(), 'arc-ledger-test-'));
  const path = join(dir, 'test.sqlite');
  try {
    const a = new Ledger(path), b = new Ledger(path);
    a.claim('crash-pending'); a.reserve(5n, 8n);
    assert.throws(() => b.claim('other'), /recovery/); a.close(); b.close();
    const c = new Ledger(path);
    assert.throws(() => c.claim('crash-pending'), /replay/);
    assert.throws(() => c.claim('other'), /recovery/);
    assert.throws(() => c.reserve(5n, 8n), /budget/);
    c.close();
  } finally { rmSync(dir, { recursive: true, force: true }); }
});
test('settlement disabled prevents SDK write', async () => {
  const f = fixture(), disabled = createHandlers({ ...config, settlementEnabled: false }, f.ledger, f.sdk, { 'eip155:5042': { getCode: async () => '0x' } });
  assert.equal((await disabled.handle('settle', await body())).errorReason, 'settlement_disabled'); assert.equal(f.counts().writes, 0); f.ledger.close();
});
test('ambiguous post-broadcast error stays pending and prevents new authorization', async () => {
  const ledger = new Ledger(':memory:'), context = new AsyncLocalStorage();
  const sdk = { verify: async () => ({ isValid: true }), settle: async () => { context.getStore().started = true; throw new Error('receipt_timeout'); } };
  const service = createHandlers(config, ledger, sdk, { 'eip155:5042': { getCode: async () => '0x' } }, context);
  assert.equal((await service.handle('settle', await body())).success, false);
  assert.equal((await service.handle('settle', await body())).errorReason, 'settlement_busy_or_recovery_required');
  ledger.close();
});
test('bounded writer checks contract, gas, fees, balance, budget and records tx', async () => {
  const ledger = new Ledger(':memory:'), context = new AsyncLocalStorage(); let writes = 0;
  const client = { chain: { id: 5042 }, getChainId: async () => 5042, estimateContractGas: async () => 100000n,
    estimateFeesPerGas: async () => ({ maxFeePerGas: 2n, maxPriorityFeePerGas: 1n }), getBalance: async () => 10n ** 18n };
  const wallet = { account, writeContract: async args => { writes++; assert.equal(args.gas, config.gasLimit); assert.equal(args.maxFeePerGas, config.maxFeePerGas); return '0x' + 'ab'.repeat(32); } };
  const write = boundedWriter({ client, wallet, config, ledger, context }), args = { address: USDC, functionName: 'transferWithAuthorization' };
  await assert.rejects(write(args), /disabled/);
  await context.run({ id: 'x', started: false }, async () => {
    await assert.rejects(write({ ...args, address: account.address }), /unauthorized/);
    client.estimateContractGas = async () => config.gasLimit + 1n; await assert.rejects(write(args), /gas_limit/);
    client.estimateContractGas = async () => 100000n; client.estimateFeesPerGas = async () => ({ maxFeePerGas: config.maxFeePerGas + 1n }); await assert.rejects(write(args), /fee_cap/);
    client.estimateFeesPerGas = async () => ({ maxFeePerGas: 2n, maxPriorityFeePerGas: 1n });
    client.getBalance = async () => 0n; await assert.rejects(write(args), /insufficient_gas_balance/);
    client.getBalance = async () => 10n ** 18n;
    assert.match(await write(args), /^0x/); await assert.rejects(write(args), /unauthorized/);
  }); assert.equal(writes, 1); ledger.close();
});
test('HTTP protocol supported and authenticated verify/settle, no unauthorized SDK writes', async () => {
  const f = fixture(), s = httpServer(f.service, config.token); await new Promise(r => s.listen(0, '127.0.0.1', r));
  const url = 'http://127.0.0.1:' + s.address().port;
  try {
    const supported = await (await fetch(url + '/supported')).json(); assert.deepEqual(supported.kinds.map(k => k.network), config.networks);
    for (const path of ['/verify', '/settle']) assert.equal((await fetch(url + path, { method: 'POST', body: '{}' })).status, 401);
    assert.equal(f.counts().writes, 0);
    const res = await fetch(url + '/verify', { method: 'POST', headers: { authorization: 'Bearer ' + config.token, 'content-type': 'application/json' }, body: JSON.stringify(await body()) });
    assert.equal(res.status, 200); assert.equal((await res.json()).isValid, true);
  } finally { await new Promise(r => s.close(r)); f.ledger.close(); }
});
