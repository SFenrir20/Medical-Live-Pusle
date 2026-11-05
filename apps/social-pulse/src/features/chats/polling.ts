/** One request at a time; catch up on resume without accumulating background polls. */
export function pollVisible(
  work: (signal: AbortSignal) => Promise<void>,
  interval: number,
  onError: (error: unknown) => void,
  initialDelay = 0,
) {
  const page = document;
  const browser = window;
  const controller = new AbortController();
  let timer: ReturnType<typeof setTimeout>;
  let running = false;
  let catchUp = false;

  const poll = async () => {
    if (controller.signal.aborted) return;
    if (running) {
      catchUp = true;
      return;
    }
    running = true;
    try {
      if (!page.hidden && navigator.onLine !== false) await work(controller.signal);
    } catch (error) {
      if (!controller.signal.aborted) onError(error);
    } finally {
      running = false;
      if (!controller.signal.aborted) {
        timer = setTimeout(poll, catchUp ? 0 : interval);
        catchUp = false;
      }
    }
  };
  const resume = () => {
    if (page.hidden || navigator.onLine === false) return;
    clearTimeout(timer);
    void poll();
  };
  page.addEventListener("visibilitychange", resume);
  browser.addEventListener("online", resume);
  browser.addEventListener("focus", resume);
  timer = setTimeout(poll, initialDelay);
  return () => {
    controller.abort();
    clearTimeout(timer);
    page.removeEventListener("visibilitychange", resume);
    browser.removeEventListener("online", resume);
    browser.removeEventListener("focus", resume);
  };
}
