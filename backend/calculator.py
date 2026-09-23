"""Расчёт плана из пяти назначений {measure_id, district_id}.

Все денежные значения и эффекты вычисляются через Decimal. Эффекты
складываются, затем применяются синергии внутри каждого района и ограничение
показателей диапазоном 0..100. Score — среднее всех показателей всех районов.
Недопустимый план вызывает ValueError; входные данные не изменяются.
"""

import json
from collections import Counter
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


DATA_PATH = Path(__file__).with_name("data.json")


def _number(value):
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def calculate_plan(selections: list[dict[str, str]]) -> dict:
    """Вернуть бюджет, Score, таблицу до/после и число показателей < 40.

    Одна запись назначает одну меру одному району. Повтор той же пары запрещён;
    одну меру можно назначить разным районам с оплатой каждого назначения.
    Лимит направления считается по назначениям во всём плане.
    """
    if not isinstance(selections, list) or len(selections) != 5:
        raise ValueError("План должен содержать ровно 5 назначений мероприятий.")

    with DATA_PATH.open(encoding="utf-8") as stream:
        data = json.load(stream, parse_float=Decimal, parse_int=Decimal)
    districts = {item["id"]: item for item in data["districts"]}
    measures = {item["id"]: item for item in data["measures"]}
    metrics = data["metrics"]
    rules = data["rules"]
    budget_limit = rules["budget"]
    direction_counts = Counter()
    assigned = {district_id: set() for district_id in districts}
    budget_spent = Decimal(0)
    selected = []

    for index, selection in enumerate(selections, start=1):
        if not isinstance(selection, dict):
            raise ValueError(f"Назначение {index}: ожидается словарь.")
        measure_id = selection.get("measure_id")
        district_id = selection.get("district_id")
        if not isinstance(measure_id, str) or measure_id not in measures:
            raise ValueError(f"Назначение {index}: неизвестное мероприятие.")
        if not isinstance(district_id, str) or district_id not in districts:
            raise ValueError(f"Назначение {index}: неизвестный район.")
        if measure_id in assigned[district_id]:
            raise ValueError(f"Повтор мероприятия {measure_id} в районе {district_id}.")
        assigned[district_id].add(measure_id)
        measure = measures[measure_id]
        selected.append((district_id, measure))
        direction_counts[measure["direction"]] += 1
        budget_spent += measure["cost"]

    for direction, count in direction_counts.items():
        if count > rules["max_per_direction"]:
            raise ValueError(f"В направлении {direction} больше 2 мероприятий.")
    if budget_spent > budget_limit:
        raise ValueError(f"Бюджет превышен: {budget_spent} из {budget_limit}.")

    before = {key: dict(item["indicators"]) for key, item in districts.items()}
    after = {key: dict(indicators) for key, indicators in before.items()}
    for district_id, measure in selected:
        for metric, effect in measure["effects"].items():
            after[district_id][metric] += effect

    applied_synergies = []
    for district_id, measure_ids in assigned.items():
        for synergy in data["synergies"]:
            if set(synergy["measure_ids"]).issubset(measure_ids):
                for metric, effect in synergy["effects"].items():
                    after[district_id][metric] += effect
                applied_synergies.append({
                    "synergy_id": synergy["id"], "district_id": district_id,
                })

    comparison = []
    critical_by_district = []
    for district_id, district in districts.items():
        for metric in metrics:
            after[district_id][metric] = min(
                rules["indicator_max"],
                max(rules["indicator_min"], after[district_id][metric]),
            )
            old = before[district_id][metric]
            new = after[district_id][metric]
            comparison.append({
                "district_id": district_id, "district": district["name"],
                "metric_id": metric, "metric": metrics[metric],
                "before": _number(old), "after": _number(new),
                "delta": _number(new - old),
                "critical_before": old < rules["critical_threshold"],
                "critical_after": new < rules["critical_threshold"],
            })
        critical_by_district.append({
            "district_id": district_id,
            "before": sum(v < rules["critical_threshold"] for v in before[district_id].values()),
            "after": sum(v < rules["critical_threshold"] for v in after[district_id].values()),
        })

    count = Decimal(len(districts) * len(metrics))
    base_score = sum(sum(values.values()) for values in before.values()) / count
    score = sum(sum(values.values()) for values in after.values()) / count
    return {
        "budget_limit": _number(budget_limit),
        "budget_spent": _number(budget_spent),
        "budget_remaining": _number(budget_limit - budget_spent),
        "direction_counts": dict(direction_counts),
        "base_score": _number(base_score),
        "score": _number(score),
        "score_delta": _number(score - base_score),
        "comparison": comparison,
        "critical_counts": {
            "before": sum(row["before"] for row in critical_by_district),
            "after": sum(row["after"] for row in critical_by_district),
            "by_district": critical_by_district,
        },
        "applied_synergies": applied_synergies,
    }


if __name__ == "__main__":
    with DATA_PATH.open(encoding="utf-8") as stream:
        example = json.load(stream)["test_example"]
    print(json.dumps(calculate_plan(example["selections"]), ensure_ascii=False, indent=2))
