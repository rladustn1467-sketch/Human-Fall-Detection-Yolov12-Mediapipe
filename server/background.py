"""The server's background steps (every second: incident timers, SMS, Telegram, push), run one by one so that an
error in one step is only logged and never stops the others (audit 2026-10-29, E-4)."""


def run_each(steps, log=print):
    """steps: [(name, function)]. Runs every step; returns how many failed."""
    errors = 0
    for name, step in steps:
        try:
            step()
        except Exception as e:  # 한 단계의 오류가 다른 단계를 막지 않도록 기록만 함
            errors += 1
            log(f"[background] {name} 처리 오류 (다른 처리는 계속): {type(e).__name__}: {e}")
    return errors
