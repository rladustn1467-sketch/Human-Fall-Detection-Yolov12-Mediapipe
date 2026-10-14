// 몇 초마다 서버에서 값을 가져와 구독한 화면들에 알려 주는 공통 모듈
//   const poller = createPoller(() => api.latestEvents(1), 3);
//   const stop = poller.subscribe((state) => { ... state.data / state.error ... });
//   poller.start();   poller.refreshNow();   stop();

export function createPoller(fetchFn, intervalSeconds) {
  const listeners = new Set();
  let timer = null;
  let running = false;
  let inFlight = false;
  // 마지막 결과: { data, error, fetchedAt }
  let last = { data: null, error: null, fetchedAt: 0 };

  function notify() {
    listeners.forEach((listener) => listener(last));
  }

  async function tick() {
    if (inFlight) return; // 이전 요청이 끝나기 전에는 새로 보내지 않음
    inFlight = true;
    try {
      last = { data: await fetchFn(), error: null, fetchedAt: Date.now() };
    } catch (error) {
      // 서버 연결이 잠시 끊겨도 마지막으로 받은 값은 유지
      last = { data: last.data, error, fetchedAt: last.fetchedAt };
    } finally {
      inFlight = false;
    }
    notify();
  }

  function schedule() {
    clearTimeout(timer);
    if (running) timer = setTimeout(async () => { await tick(); schedule(); }, intervalSeconds * 1000);
  }

  // 다른 앱을 보다가 돌아오면 바로 새로고침
  document.addEventListener("visibilitychange", () => {
    if (running && document.visibilityState === "visible") refreshNow();
  });

  async function refreshNow() {
    await tick();
    schedule();
  }

  return {
    start() {
      if (running) return;
      running = true;
      refreshNow();
    },
    stop() {
      running = false;
      clearTimeout(timer);
    },
    refreshNow,
    subscribe(listener) {
      listeners.add(listener);
      if (last.fetchedAt || last.error) listener(last);
      return () => listeners.delete(listener);
    },
    get last() { return last; },
  };
}
