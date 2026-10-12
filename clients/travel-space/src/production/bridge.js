export async function invoke(operation, payload = {}) {
  const host = window.webkit?.messageHandlers?.quantum;
  if (!host) throw new Error('请在 Quantum 应用中打开此界面。');
  return host.postMessage({operation, ...payload});
}

export function errorMessage(error) {
  return error?.message || String(error || '暂时无法连接，请重试。');
}
