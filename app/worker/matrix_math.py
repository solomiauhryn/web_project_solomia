import random
from typing import Callable, Optional


class TaskCancelledError(Exception):
    pass


class SingularMatrixError(Exception):
    pass


def generate_invertible_matrix(size: int, seed: Optional[int] = None) -> list[list[float]]:
    rng = random.Random(seed)
    matrix: list[list[float]] = []
    for i in range(size):
        row: list[float] = []
        row_sum = 0.0
        for j in range(size):
            if i != j:
                val = round(rng.uniform(-5.0, 5.0), 4)
                row.append(val)
                row_sum += abs(val)
            else:
                row.append(0.0)
        sign = 1.0 if rng.random() >= 0.5 else -1.0
        row[i] = round(sign * (row_sum + rng.uniform(2.0, 10.0)), 4)
        matrix.append(row)
    return matrix


def extract_matrix_preview(matrix: list[list[float]], max_dim: int = 5) -> list[list[float]]:
    limit = min(len(matrix), max_dim)
    return [
        [round(matrix[i][j], 6) for j in range(limit)]
        for i in range(limit)
    ]


def compute_residual_norm(
    original: list[list[float]],
    inverse: list[list[float]],
    sample_rows: int = 10,
) -> float:
    n = len(original)
    rows_to_check = min(n, sample_rows)
    max_row_err = 0.0
    for i in range(rows_to_check):
        row_err = 0.0
        orig_row = original[i]
        for j in range(n):
            dot_val = 0.0
            for k in range(n):
                dot_val += orig_row[k] * inverse[k][j]
            target = 1.0 if i == j else 0.0
            row_err += abs(dot_val - target)
        if row_err > max_row_err:
            max_row_err = row_err
    return round(max_row_err, 10)


def invert_matrix_gauss_jordan(
    matrix: list[list[float]],
    progress_callback: Optional[Callable[[int, str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> tuple[list[list[float]], float]:
    n = len(matrix)
    if n == 0 or any(len(row) != n for row in matrix):
        raise ValueError("Матриця повинна бути квадратною")

    if progress_callback:
        progress_callback(5, f"Ініціалізація розширеної матриці {n}x{2 * n}")

    aug: list[list[float]] = []
    for i in range(n):
        if cancel_check and cancel_check():
            raise TaskCancelledError("Задачу скасовано користувачем")
        ident_row = [0.0] * n
        ident_row[i] = 1.0
        aug.append([float(x) for x in matrix[i]] + ident_row)

    report_step = max(1, n // 25)
    two_n = 2 * n

    for col in range(n):
        if cancel_check and cancel_check():
            raise TaskCancelledError("Задачу скасовано користувачем")

        pivot_row = col
        max_val = abs(aug[col][col])
        for r in range(col + 1, n):
            val = abs(aug[r][col])
            if val > max_val:
                max_val = val
                pivot_row = r

        if max_val < 1e-12:
            raise SingularMatrixError(
                f"Матриця є виродженою (нульовий ведучий елемент у стовпці {col + 1})"
            )

        if pivot_row != col:
            aug[col], aug[pivot_row] = aug[pivot_row], aug[col]

        pivot = aug[col][col]
        inv_pivot = 1.0 / pivot
        pivot_line = aug[col]
        for j in range(col, two_n):
            pivot_line[j] *= inv_pivot

        for r in range(n):
            if r != col:
                factor = aug[r][col]
                if factor != 0.0:
                    target_line = aug[r]
                    for j in range(col, two_n):
                        target_line[j] -= factor * pivot_line[j]

        if progress_callback and ((col + 1) % report_step == 0 or col == n - 1):
            pct = 10 + int(((col + 1) / n) * 80)
            progress_callback(
                pct,
                f"Елімінація Гауса-Жордана: оброблено рядок {col + 1} з {n}",
            )

    if cancel_check and cancel_check():
        raise TaskCancelledError("Задачу скасовано користувачем")

    if progress_callback:
        progress_callback(92, "Виділення оберненої матриці та перевірка точності")

    inverse = [row[n:two_n] for row in aug]
    residual = compute_residual_norm(matrix, inverse)

    if progress_callback:
        progress_callback(100, "Обчислення успішно завершено")

    return inverse, residual
