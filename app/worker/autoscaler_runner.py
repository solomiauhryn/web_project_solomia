import time
from sqlmodel import Session
from app.core.database import engine
from app.services.autoscaler import evaluate_autoscale


def run_autoscaler_loop(interval_sec: int = 5) -> None:
    while True:
        try:
            with Session(engine) as session:
                evaluate_autoscale(session)
        except Exception:
            pass
        time.sleep(interval_sec)


if __name__ == "__main__":
    run_autoscaler_loop()
