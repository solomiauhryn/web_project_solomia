import sys
import time
import httpx


def run_verification(base_url: str = "http://localhost:8000") -> int:
    print(f"=== Перевірка кластера: {base_url} ===")
    with httpx.Client(base_url=base_url, verify=False, timeout=15.0) as client:
        responders: list[str] = []
        for i in range(6):
            resp = client.get("/api/cluster/node")
            resp.raise_for_status()
            host = resp.headers.get("X-Served-By", resp.json().get("instance_hostname", "unknown"))
            responders.append(host)
        print(f"1. Балансування (серія з 6 запитів): {' -> '.join(responders)}")

        login_resp = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin123"},
        )
        login_resp.raise_for_status()
        token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print("2. Авторизація адміністратора (JWT): успішно")

        reject_resp = client.post(
            "/api/tasks",
            json={"matrix_size": 850, "generate_random": True},
            headers=headers,
        )
        print(f"3. Перевірка ліміту трудомісткості (N=850 > 600): HTTP {reject_resp.status_code}")

        created_resp = client.post(
            "/api/tasks",
            json={"matrix_size": 12, "generate_random": True, "execute_immediately": True},
            headers=headers,
        )
        created_resp.raise_for_status()
        task_data = created_resp.json()
        print(
            f"4. Тестове обернення матриці 12x12: статус={task_data['status']}, "
            f"нев'язка={task_data['residual_norm']}, час={task_data['execution_time_sec']}с"
        )

        ov_resp = client.get("/api/admin/overview", headers=headers)
        ov_resp.raise_for_status()
        ov = ov_resp.json()
        print(
            f"5. Моніторинг: CPU={ov['system_metrics']['cpu_percent']}%, "
            f"RAM={ov['system_metrics']['memory_percent']}%, "
            f"Воркери={ov['autoscaler']['current_workers']}/{ov['autoscaler']['max_workers']}"
        )

    print("=== Усі перевірки пройдено успішно ===")
    return 0


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    sys.exit(run_verification(target))
