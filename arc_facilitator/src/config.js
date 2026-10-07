import { isAddress } from 'viem';
import { NETWORKS } from './probe.js';
export function loadConfig(env = process.env) {
  const networks = (env.ARC_NETWORKS || 'eip155:5042002').split(',');
  if (!networks.length || new Set(networks).size !== networks.length || networks.some(n => !NETWORKS[n])) throw new Error('unsupported_network');
  const recipients = (env.ARC_ALLOWED_PAY_TO || '').split(',').map(s => s.toLowerCase());
  if (recipients.some(a => !isAddress(a) || /^0x0{40}$/.test(a))) throw new Error('allowed_recipient_required');
  const integer = (key, fallback, max) => {
    const s = env[key] || fallback;
    if (!/^[1-9][0-9]*$/.test(s) || BigInt(s) > max) throw new Error('invalid_' + key);
    return BigInt(s);
  };
  if (!/^0x[0-9a-fA-F]{64}$/.test(env.ARC_FACILITATOR_PRIVATE_KEY || '')) throw new Error('dedicated_key_required');
  if ((env.ARC_FACILITATOR_API_TOKEN || '').length < 32) throw new Error('api_token_required');
  if (!['true', 'false', undefined].includes(env.ARC_SETTLEMENT_ENABLED)) throw new Error('invalid_settlement_flag');
  return {
    networks, recipients, key: env.ARC_FACILITATOR_PRIVATE_KEY, token: env.ARC_FACILITATOR_API_TOKEN,
    settlementEnabled: env.ARC_SETTLEMENT_ENABLED === 'true',
    port: Number(integer('ARC_PORT', '3402', 65535n)), dbPath: env.ARC_DB_PATH || './state/facilitator.sqlite',
    gasLimit: integer('ARC_GAS_LIMIT', '200000', 1000000n),
    maxFeePerGas: integer('ARC_MAX_FEE_PER_GAS_WEI', '10000000000', 100000000000n),
    dailyGasBudget: integer('ARC_DAILY_GAS_BUDGET_WEI', '10000000000000000', 100000000000000000n),
    maxAmount: integer('ARC_MAX_AMOUNT', '100000', 100000000n),
    rpc: { 'eip155:5042': env.ARC_MAINNET_RPC_URL || NETWORKS['eip155:5042'].rpc, 'eip155:5042002': env.ARC_TESTNET_RPC_URL || NETWORKS['eip155:5042002'].rpc },
  };
}
