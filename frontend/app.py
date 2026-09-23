"""Экран симулятора. Запуск: streamlit run frontend/app.py.

Опциональный calculator.py можно разместить в frontend/, backend/ или корне.
Его calculate(decisions) принимает список {measure_id, district, cost} и возвращает
словарь той же структуры, что demo_calculate ниже. Стоимость — в млн ₸.
"""

from importlib import import_module
from pathlib import Path
import sys

import streamlit as st


ROOT = Path(__file__).resolve().parents[1]
for directory in (ROOT, ROOT / "backend"):
    if str(directory) not in sys.path:
        sys.path.append(str(directory))

try:
    calculator = import_module("calculator")
except ModuleNotFoundError as exc:
    if exc.name != "calculator":
        raise
    calculator = None

# Временные названия, цены и эффекты; заменить реальным каталогом.
CATALOG = {
    "M1": {"name": "Ремонт дорог", "cost": 220},
    "M2": {"name": "Уличное освещение", "cost": 90},
    "M3": {"name": "Озеленение дворов", "cost": 70},
    "M4": {"name": "Детские площадки", "cost": 60},
    "M5": {"name": "Обновление поликлиник", "cost": 180},
    "M6": {"name": "Ремонт школ", "cost": 200},
    "M7": {"name": "Новые автобусные маршруты", "cost": 140},
    "M8": {"name": "Благоустройство парков", "cost": 110},
    "M9": {"name": "Раздельный сбор отходов", "cost": 80},
    "M10": {"name": "Модернизация ливневой канализации", "cost": 160},
    "M11": {"name": "Спортивные площадки", "cost": 100},
    "M12": {"name": "Городская система обращений", "cost": 120},
}
DISTRICTS = ["Нура", "Сарыарка", "Алматы", "Байконыр", "Есиль", "Сарайшық", "Весь город"]
DEMO = [("M7", "Нура"), ("M8", "Нура"), ("M10", "Нура"), ("M12", "Весь город"), ("M5", "Сарыарка")]
BUDGET = 1_000
BASELINE = {"Транспорт": 42, "Экология": 48, "Инфраструктура": 38, "Здравоохранение": 46, "Городские сервисы": 55}
EFFECTS = {
    "M1": ("Транспорт", 10), "M2": ("Инфраструктура", 8),
    "M3": ("Экология", 7), "M4": ("Инфраструктура", 5),
    "M5": ("Здравоохранение", 14), "M6": ("Инфраструктура", 12),
    "M7": ("Транспорт", 13), "M8": ("Экология", 11),
    "M9": ("Экология", 8), "M10": ("Инфраструктура", 15),
    "M11": ("Здравоохранение", 6), "M12": ("Городские сервисы", 12),
}


def demo_calculate(decisions):
    """Детерминированная заглушка; район пока не влияет на результат."""
    after = BASELINE.copy()
    for decision in decisions:
        indicator, gain = EFFECTS[decision["measure_id"]]
        after[indicator] = min(100, after[indicator] + gain)
    rows = [
        {"Показатель": name, "До": before, "После": after[name], "Изменение": after[name] - before}
        for name, before in BASELINE.items()
    ]
    return {
        "score": round(sum(after.values()) / len(after), 1),
        "indicators": rows,
        "critical_before": sum(value < 50 for value in BASELINE.values()),
        "critical_after": sum(value < 50 for value in after.values()),
        "ai_analysis": "AI-разбор пока не подключён. Здесь появятся объяснение результата, риски и рекомендации по выбранным решениям.",
    }


def restore_demo():
    for index, (measure, district) in enumerate(DEMO):
        st.session_state[f"measure_{index}"] = measure
        st.session_state[f"district_{index}"] = district
    st.session_state.pop("evaluation", None)


def money(value):
    return f"{value:,}".replace(",", " ") + " млн ₸"


def main():
    st.set_page_config(page_title="Аким: пять решений для города", page_icon="🏙️", layout="wide")
    st.title("Аким: пять решений для города")
    st.write("Выберите пять мероприятий и территории их реализации в пределах городского бюджета.")
    st.info("Демо-каталог: названия мероприятий, цены и бюджет условные.")
    if calculator is None:
        st.caption("Расчёт работает на заглушке: показатели от 0 до 100, больше — лучше. Критический уровень — ниже 50. Районы пока не влияют на расчёт.")

    st.button("Восстановить демо-пример", on_click=restore_demo)
    decisions = []
    for index, (default_measure, default_district) in enumerate(DEMO):
        st.session_state.setdefault(f"measure_{index}", default_measure)
        st.session_state.setdefault(f"district_{index}", default_district)
        measure_col, district_col, cost_col = st.columns([3, 2, 1])
        with measure_col:
            measure = st.selectbox(
                f"Мероприятие {index + 1}", list(CATALOG), key=f"measure_{index}",
                format_func=lambda code: f"{code} — {CATALOG[code]['name']}",
            )
        with district_col:
            district = st.selectbox(f"Территория {index + 1}", DISTRICTS, key=f"district_{index}")
        cost = CATALOG[measure]["cost"]
        with cost_col:
            st.metric("Стоимость", money(cost))
        decisions.append({"measure_id": measure, "district": district, "cost": cost})

    spent = sum(item["cost"] for item in decisions)
    remaining = BUDGET - spent
    budget_col, spent_col, remaining_col = st.columns(3)
    budget_col.metric("Бюджет", money(BUDGET))
    spent_col.metric("Потрачено", money(spent))
    remaining_col.metric("Осталось", money(remaining))
    st.progress(min(spent / BUDGET, 1.0))

    unique = len({item["measure_id"] for item in decisions}) == 5
    if not unique:
        st.warning("Выберите пять разных мероприятий.")
    if remaining < 0:
        st.error(f"Бюджет превышен на {money(-remaining)}. Измените набор мероприятий.")

    signature = tuple((item["measure_id"], item["district"], item["cost"]) for item in decisions)
    previous = st.session_state.get("evaluation")
    if previous and previous["signature"] != signature:
        st.session_state.pop("evaluation")

    if st.button("Оценить решения", type="primary", disabled=not unique or remaining < 0):
        st.session_state.pop("evaluation", None)
        try:
            with st.spinner("Оцениваем решения…"):
                result = calculator.calculate(decisions) if calculator is not None else demo_calculate(decisions)
                required = {"score", "indicators", "critical_before", "critical_after", "ai_analysis"}
                if not isinstance(result, dict) or not required.issubset(result):
                    raise ValueError("Калькулятор вернул результат в неподдерживаемом формате.")
                st.session_state["evaluation"] = {"signature": signature, "result": result}
        except Exception as exc:
            st.error(f"Не удалось оценить решения: {exc}")

    st.subheader("Результаты")
    evaluation = st.session_state.get("evaluation")
    if evaluation is None:
        st.caption("Нажмите «Оценить решения», чтобы увидеть Score, показатели до/после и AI-разбор.")
        return

    result = evaluation["result"]
    score_col, critical_col = st.columns(2)
    score_col.metric("Итоговый Score", f"{result['score']} / 100")
    critical_col.metric("Критических показателей после", result["critical_after"])
    st.caption(f"Критических показателей до: {result['critical_before']}")
    st.dataframe(result["indicators"], hide_index=True, use_container_width=True)
    st.subheader("AI-разбор")
    with st.container(border=True):
        st.write(result["ai_analysis"])


if __name__ == "__main__":
    main()
