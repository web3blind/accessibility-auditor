import { createPublicClient, http, parseAbi, hashDomain, encodeFunctionData } from 'viem';
import { pathToFileURL } from 'node:url';
export const USDC = '0x3600000000000000000000000000000000000000';
export const NETWORKS = {
  'eip155:5042': { id: 5042, name: 'Arc', rpc: 'https://rpc.mainnet.arc.io' },
  'eip155:5042002': { id: 5042002, name: 'Arc Testnet', rpc: 'https://rpc.testnet.arc.io' },
};
export const abi = parseAbi([
  'function decimals() view returns (uint8)', 'function name() view returns (string)',
  'function version() view returns (string)', 'function DOMAIN_SEPARATOR() view returns (bytes32)',
  'function authorizationState(address authorizer, bytes32 nonce) view returns (bool)',
  'function transferWithAuthorization(address from,address to,uint256 value,uint256 validAfter,uint256 validBefore,bytes32 nonce,uint8 v,bytes32 r,bytes32 s)',
]);
export function publicClient(network, url) {
  const n = NETWORKS[network];
  if (!n) throw new Error('unsupported_network');
  return createPublicClient({ chain: { id: n.id, name: n.name, nativeCurrency: { name: 'USDC', symbol: 'USDC', decimals: 18 }, rpcUrls: { default: { http: [url || n.rpc] } } }, transport: http(url || n.rpc, { timeout: 12000, retryCount: 0 }) });
}
export async function probe(network, client) {
  const n = NETWORKS[network];
  if (await client.getChainId() !== n.id) throw new Error('rpc_chain_mismatch');
  const read = functionName => client.readContract({ address: USDC, abi, functionName });
  const [decimals, name, version, domain] = await Promise.all(['decimals', 'name', 'version', 'DOMAIN_SEPARATOR'].map(read));
  if (decimals !== 6 || name !== 'USDC' || version !== '2') throw new Error('unexpected_usdc_metadata');
  const expected = hashDomain({ domain: { name, version, chainId: n.id, verifyingContract: USDC }, types: { EIP712Domain: [{ name: 'name', type: 'string' }, { name: 'version', type: 'string' }, { name: 'chainId', type: 'uint256' }, { name: 'verifyingContract', type: 'address' }] } });
  if (domain.toLowerCase() !== expected.toLowerCase()) throw new Error('domain_mismatch');
  const zero32 = '0x' + '00'.repeat(32), from = '0x0000000000000000000000000000000000000001';
  const used = await client.readContract({ address: USDC, abi, functionName: 'authorizationState', args: [from, zero32] });
  // Force the expired-authorization branch. Its explicit EIP3009 revert proves
  // selector dispatch without signing, changing balances, or submitting a tx.
  let evidence;
  try {
    await client.call({ to: USDC, data: encodeFunctionData({ abi, functionName: 'transferWithAuthorization', args: [from, from, 0n, 0n, 1n, zero32, 27, zero32, zero32] }) });
    throw new Error('unexpected_transfer_call_success');
  } catch (e) {
    const message = e.shortMessage + ' ' + e.message;
    if (!/authorization is expired/i.test(message)) throw new Error('eip3009_not_proven');
    evidence = 'FiatTokenV2: authorization is expired';
  }
  return { network, chainId: n.id, asset: USDC, decimals, name, version, domain, authorizationState: used, transferWithAuthorization: evidence, readOnly: true };
}
if (import.meta.url === pathToFileURL(process.argv[1] || '').href) {
  for (const network of Object.keys(NETWORKS)) {
    try { console.log(JSON.stringify(await probe(network, publicClient(network, process.env[network.endsWith('5042002') ? 'ARC_TESTNET_RPC_URL' : 'ARC_MAINNET_RPC_URL'])))); }
    catch (e) { console.log(JSON.stringify({ network, available: false, reason: ['rpc_chain_mismatch', 'unexpected_usdc_metadata', 'domain_mismatch', 'eip3009_not_proven'].includes(e.message) ? e.message : 'rpc_unavailable_or_rate_limited' })); }
  }
}
