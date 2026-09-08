import { useEffect, useRef } from 'react';

/**
 * 通用轮询 hook：enabled 为 true 时每隔 interval 调用一次 fn。
 * unmount 或 enabled 变 false 时自动停止并清理定时器。
 */
export function usePolling(fn: () => void | Promise<void>, interval: number, enabled: boolean) {
  const fnRef = useRef(fn);
  fnRef.current = fn;

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    const timer = window.setInterval(async () => {
      if (cancelled) return;
      try {
        await fnRef.current();
      } catch {
        /* 轮询失败静默，下一轮继续 */
      }
    }, interval);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [interval, enabled]);
}
