import { AsyncLocalStorage } from 'node:async_hooks';
import { isDeepStrictEqual } from 'node:util';
import { createWalletClient, http, publicActions, isAddress } from 'viem';
import { privateKeyToAccount } from 'viem/accounts';
import { x402Facilitator } from '@x402/core/facilitator';
import { ExactEvmScheme } from '@x402/evm/exact/facilitator';
import { toFacilitatorEvmSigner } from '@x402/evm';
import { publicClient, probe, USDC } from './probe.js';
const digits = x => typeof x === 'string' && /^(0|[1-9][0-9]*)$/.test(x) && x.length <= 78;
export function validate(body, config) {
  const p = body?.paymentPayload, r = body?.paymentRequirements, a = p?.payload?.authorization;
  if (body?.x402Version !== 2 || p?.x402Version !== 2) throw new Error('unsupported_version');
  if (!r || !config.networks.includes(r.network) || r.scheme !== 'exact' || r.asset?.toLowerCase() !== USDC.toLowerCase()) throw new Error('unsupported_payment_requirements');
  if (!isAddress(r.payTo || '') || !config.recipients.includes(r.payTo.toLowerCase())) throw new Error('recipient_not_allowed');
  if (!digits(r.amount) || BigInt(r.amount) < 1n || BigInt(r.amount) > config.maxAmount) throw new Error('amount_not_allowed');
  if (r.extra?.name !== 'USDC' || r.extra?.version !== '2' || (r.extra.assetTransferMethod && r.extra.assetTransferMethod !== 'eip3009')) throw new Error('invalid_eip712_domain');
  if (!Number.isInteger(r.maxTimeoutSeconds) || r.maxTimeoutSeconds < 1 || r.maxTimeoutSeconds > 300) throw new Error('invalid_timeout');
  for (const k of ['network', 'scheme', 'asset', 'amount', 'payTo', 'maxTimeoutSeconds']) if (p.accepted?.[k] !== r[k]) throw new Error('accepted_mismatch');
  if (!isDeepStrictEqual(p.accepted.extra, r.extra)) throw new Error('accepted_mismatch');
  if (p.extensions && Object.keys(p.extensions).length) throw new Error('extensions_not_supported');
  if (!a || Object.keys(p.payload).some(k => !['authorization', 'signature'].includes(k)) || !/^0x[0-9a-fA-F]{130}$/.test(p.payload.signature || '')) throw new Error('only_eoa_eip3009_supported');
  if (!isAddress(a.from || '') || !isAddress(a.to || '') || a.to.toLowerCase() !== r.payTo.toLowerCase()) throw new Error('authorization_recipient_mismatch');
  if (!/^0x[0-9a-fA-F]{64}$/.test(a.nonce || '') || !['value', 'validAfter', 'validBefore'].every(k => digits(a[k]))) throw new Error('invalid_authorization');
  const now = BigInt(Math.floor(Date.now() / 1000));
  if (BigInt(a.value) !== BigInt(r.amount) || BigInt(a.validAfter) >= now || BigInt(a.validBefore) < now + 6n || BigInt(a.validBefore) > now + BigInt(r.maxTimeoutSeconds)) throw new Error('invalid_authorization_bounds');
  return { p, r, a, id: `${r.network}:${USDC.toLowerCase()}:${a.from.toLowerCase()}:${a.nonce.toLowerCase()}` };
}
export function failure(operation, reason, network = '') {
  return operation === 'verify' ? { isValid: false, invalidReason: reason } : { success: false, errorReason: reason, transaction: '', network };
}
export function boundedWriter({ client, wallet, config, ledger, context }) {
  return async args => {
    const ctx = context.getStore();
    if (!ctx || !config.settlementEnabled) throw new Error('settlement_disabled');
    if (ctx.started || args.address.toLowerCase() !== USDC.toLowerCase() || args.functionName !== 'transferWithAuthorization' || args.dataSuffix) throw new Error('unauthorized_write');
    if (await client.getChainId() !== client.chain.id) throw new Error('rpc_chain_mismatch');
    const estimate = await client.estimateContractGas({ ...args, account: wallet.account });
    if (estimate > config.gasLimit) throw new Error('gas_limit_exceeded');
    const fee = await client.estimateFeesPerGas();
    if (!fee.maxFeePerGas || fee.maxFeePerGas > config.maxFeePerGas || fee.maxPriorityFeePerGas > config.maxFeePerGas) throw new Error('gas_fee_cap_exceeded');
    const reserve = config.gasLimit * config.maxFeePerGas;
    if (await client.getBalance({ address: wallet.account.address }) < reserve) throw new Error('insufficient_gas_balance');
    ledger.reserve(reserve, config.dailyGasBudget);
    // Once RPC submission begins any ambiguous error permanently blocks automatic
    // retries until an operator reconciles the persisted nonce/transaction.
    ctx.started = true;
    const hash = await wallet.writeContract({ ...args, gas: config.gasLimit, maxFeePerGas: config.maxFeePerGas, maxPriorityFeePerGas: fee.maxPriorityFeePerGas || 0n });
    ledger.tx(ctx.id, hash);
    return hash;
  };
}
export async function createService(config, ledger) {
  const account = privateKeyToAccount(config.key), context = new AsyncLocalStorage(), clients = {};
  const sdk = new x402Facilitator();
  for (const network of config.networks) {
    const client = publicClient(network, config.rpc[network]);
    await probe(network, client); // refuse to advertise unproven chains/assets
    clients[network] = client;
    const wallet = createWalletClient({ account, chain: client.chain, transport: http(config.rpc[network], { timeout: 12000, retryCount: 0 }) }).extend(publicActions);
    const signer = toFacilitatorEvmSigner({ ...client, address: account.address });
    signer.writeContract = boundedWriter({ client, wallet, config, ledger, context });
    signer.sendTransaction = async () => { throw new Error('arbitrary_transactions_disabled'); };
    sdk.register(network, new ExactEvmScheme(signer, { simulateInSettle: true, eip6492AllowedFactories: [] }));
  }
  return createHandlers(config, ledger, sdk, clients, context);
}
export function createHandlers(config, ledger, sdk, clients, context = new AsyncLocalStorage()) {
  return {
    supported: () => sdk.getSupported(),
    async handle(operation, body) {
      let v;
      try {
        v = validate(body, config);
        const code = await clients[v.r.network].getCode({ address: v.a.from });
        if (code && code !== '0x') throw new Error('contract_payers_disabled');
        if (operation === 'verify') {
          const result = await sdk.verify(v.p, v.r);
          return result.isValid ? { isValid: true, payer: result.payer } : failure(operation, result.invalidReason || 'invalid_payment', v.r.network);
        }
        if (!config.settlementEnabled) throw new Error('settlement_disabled');
        ledger.claim(v.id);
        const ctx = { id: v.id, started: false };
        return await context.run(ctx, async () => {
          let result;
          try {
            const verified = await sdk.verify(v.p, v.r);
            result = verified.isValid ? await sdk.settle(v.p, v.r) : failure(operation, verified.invalidReason || 'invalid_payment', v.r.network);
          } catch { result = failure(operation, 'settlement_error', v.r.network); }
          if (!ctx.started || result.success) ledger.finish(v.id, result);
          // Failure after submission stays pending. Never automatically resubmit.
          return { success: result.success, errorReason: result.errorReason, transaction: result.transaction || '', network: v.r.network, ...(result.payer && { payer: result.payer }) };
        });
      } catch (e) {
        const reason = ['authorization_replay', 'settlement_busy_or_recovery_required', 'settlement_disabled'].includes(e.message) || !v ? e.message : 'invalid_payment';
        const result = failure(operation, reason, v?.r.network || '');
        // Any unexpected error after claim remains pending for operator reconciliation.
        return result;
      }
    },
  };
}
