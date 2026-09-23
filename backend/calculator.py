"""Расчёт по «Датасет районов.pdf». Вход: пять {measure_id, district_id}.

У городской меры district_id отсутствует или None. Невалидный план вызывает
ValueError. Все вычисления через Decimal без промежуточного округления.
Score округлён до сотых для UI; *_exact — точные десятичные строки.
"""

import json
from collections import Counter
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

DATA_PATH = Path(__file__).with_name("data.json")


def load_data():
    """Загрузить единый каталог для интерфейса (обычные JSON-типы)."""
    with DATA_PATH.open(encoding="utf-8") as stream:
        return json.load(stream)


def _number(value):
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _exact(value):
    return format(value.normalize(), "f")


def _validate(selections, data):
    rules = data["rules"]
    if not isinstance(selections, list) or len(selections) != rules["selection_count"]:
        raise ValueError("План должен содержать ровно 5 мероприятий.")
    measures = {item["id"]: item for item in data["measures"]}
    districts = {item["id"] for item in data["districts"]}
    assignments = {}
    for index, selection in enumerate(selections, start=1):
        if not isinstance(selection, dict):
            raise ValueError(f"Назначение {index}: ожидается словарь.")
        measure_id = selection.get("measure_id")
        district_id = selection.get("district_id")
        if not isinstance(measure_id, str) or measure_id not in measures:
            raise ValueError(f"Назначение {index}: неизвестное мероприятие.")
        if measure_id in assignments:
            raise ValueError(f"Повтор мероприятия {measure_id}: каждая мера разрешена только один раз.")
        if measures[measure_id]["scope"] == "city":
            if district_id is not None:
                raise ValueError(f"{measure_id}: для городской меры район не указывается.")
        elif not isinstance(district_id, str) or district_id not in districts:
            raise ValueError(f"{measure_id}: укажите существующий район для районной меры.")
        assignments[measure_id] = district_id

    selected = [m for m in data["measures"] if m["id"] in assignments]
    counts = Counter(m["direction"] for m in selected)
    for direction, count in counts.items():
        if count > rules["max_per_direction"]:
            name = data["directions"][direction]
            raise ValueError(f"Направление «{name}»: {count} мероприятий, максимум 2.")
    for conflict in data["incompatibilities"]:
        first, second = conflict["measure_ids"]
        if first in assignments and second in assignments:
            if conflict["scope"] == "global" or assignments[first] == assignments[second]:
                raise ValueError(f"Несовместимы {first} и {second}: {conflict['reason']}.")
    spent = sum((m["cost"] for m in selected), Decimal(0))
    if spent > rules["budget"]:
        raise ValueError(f"Бюджет превышен: {spent} из {rules['budget']}.")
    return assignments, selected, counts, spent


def _evaluate(indicators, data):
    rules = data["rules"]
    district_scores = {
        district_id: sum(data["metric_weights"][metric] * value for metric, value in values.items())
        for district_id, values in indicators.items()
    }
    average = sum(d["population_share"] * district_scores[d["id"]] for d in data["districts"])
    minimum = min(district_scores.values())
    critical = sum(value < rules["critical_threshold"] for values in indicators.values() for value in values.values())
    score = rules["average_weight"] * average + rules["minimum_weight"] * minimum - rules["critical_penalty"] * critical
    return {"district_scores": district_scores, "average": average,
            "minimum": minimum, "critical": critical, "score": score}


def calculate_plan(selections: list[dict[str, str | None]]) -> dict:
    """Рассчитать план без изменения входа. Цены берутся только из JSON.

    measure_effects содержит эффекты после лага, до clip, отдельно от синергий.
    Это не независимый вклад меры в нелинейный Score. AI здесь не вызывается.
    """
    with DATA_PATH.open(encoding="utf-8") as stream:
        data = json.load(stream, parse_float=Decimal, parse_int=Decimal)
    assignments, selected, counts, spent = _validate(selections, data)
    rules = data["rules"]
    before = {d["id"]: dict(d["indicators"]) for d in data["districts"]}
    after = {key: dict(values) for key, values in before.items()}
    measure_effects = []
    for measure in selected:
        factor = (rules["horizon_quarters"] - measure["lag"]) / rules["horizon_quarters"]
        targets = list(after) if measure["scope"] == "city" else [assignments[measure["id"]]]
        effects = {metric: effect * factor for metric, effect in measure["effects"].items()}
        for district_id in targets:
            for metric, effect in effects.items():
                after[district_id][metric] += effect
        measure_effects.append({
            "measure_id": measure["id"], "name": measure["name"],
            "district_ids": targets, "lag": int(measure["lag"]),
            "realized_fraction": float(factor),
            "effects_before_clip": {key: float(value) for key, value in effects.items()},
        })

    applied_synergies = []
    for synergy in data["synergies"]:
        if all(measure_id in assignments for measure_id in synergy["measure_ids"]):
            district_id = assignments[synergy["measure_ids"][0]]
            for metric, effect in synergy["effects"].items():
                after[district_id][metric] += effect
            applied_synergies.append({
                "synergy_id": synergy["id"], "district_id": district_id,
                "effects_before_clip": {key: float(value) for key, value in synergy["effects"].items()},
            })

    for values in after.values():
        for metric, value in values.items():
            values[metric] = min(rules["indicator_max"], max(rules["indicator_min"], value))
    baseline = _evaluate(before, data)
    final = _evaluate(after, data)
    comparison = []
    critical_by_district = []
    district_scores = []
    for district in data["districts"]:
        district_id = district["id"]
        for metric, name in data["metrics"].items():
            old, new = before[district_id][metric], after[district_id][metric]
            comparison.append({
                "district_id": district_id, "district": district["name"],
                "metric_id": metric, "metric": name,
                "before": float(old), "after": float(new), "delta": float(new - old),
                "critical_before": old < rules["critical_threshold"],
                "critical_after": new < rules["critical_threshold"],
            })
        critical_by_district.append({
            "district_id": district_id,
            "before": sum(v < rules["critical_threshold"] for v in before[district_id].values()),
            "after": sum(v < rules["critical_threshold"] for v in after[district_id].values()),
        })
        old, new = baseline["district_scores"][district_id], final["district_scores"][district_id]
        district_scores.append({
            "district_id": district_id, "district": district["name"],
            "population_share": float(district["population_share"]),
            "before": float(old), "after": float(new), "delta": float(new - old),
        })

    return {
        "budget_limit": _number(rules["budget"]), "budget_spent": _number(spent),
        "budget_remaining": _number(rules["budget"] - spent),
        "direction_counts": dict(counts),
        "base_score": _number(baseline["score"]), "score": _number(final["score"]),
        "score_delta": _number(final["score"] - baseline["score"]),
        "base_score_exact": _exact(baseline["score"]), "score_exact": _exact(final["score"]),
        "score_delta_exact": _exact(final["score"] - baseline["score"]),
        "comparison": comparison, "district_scores": district_scores,
        "score_components": {
            phase: {
                "population_weighted_average": float(result["average"]),
                "minimum_district_score": float(result["minimum"]),
                "critical_penalty": float(rules["critical_penalty"] * result["critical"]),
            }
            for phase, result in (("before", baseline), ("after", final))
        },
        "critical_counts": {
            "before": baseline["critical"], "after": final["critical"],
            "by_district": critical_by_district,
        },
        "measure_effects": measure_effects, "applied_synergies": applied_synergies,
    }


if __name__ == "__main__":
    print(json.dumps(calculate_plan(load_data()["test_example"]["selections"]), ensure_ascii=False, indent=2))
