"""Экран симулятора. Запуск из корня: python -m streamlit run frontend/app.py."""

from pathlib import Path
import sys

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.calculator import calculate_plan, load_data

DATA = load_data()
CATALOG = {m["id"]: m for m in DATA["measures"]}
DISTRICTS = {d["id"]: d["name"] for d in DATA["districts"]}
DEMO = DATA["test_example"]["selections"]
BUDGET = DATA["rules"]["budget"]


def restore_demo():
    for index, decision in enumerate(DEMO):
        st.session_state[f"measure_{index}"] = decision["measure_id"]
        st.session_state[f"district_{index}"] = decision["district_id"] or "nura"
    st.session_state.pop("evaluation", None)


def money(value):
    return f"{value:g} усл. ед."


def main():
    st.set_page_config(page_title="Аким: пять решений для города", page_icon="🏙️", layout="wide")
    st.title("Аким: пять решений для города")
    st.write("Выберите пять мероприятий и территории их реализации в пределах городского бюджета.")
    st.info("Учебная модель на условных данных. Горизонт — 8 кварталов. Критические показатели — строго ниже 40.")
    st.button("Восстановить демо-пример", on_click=restore_demo)

    decisions = []
    for index, default in enumerate(DEMO):
        measure_key, district_key = f"measure_{index}", f"district_{index}"
        if st.session_state.get(measure_key) not in CATALOG:
            st.session_state[measure_key] = default["measure_id"]
        if st.session_state.get(district_key) not in DISTRICTS:
            st.session_state[district_key] = default["district_id"] or "nura"
        measure_col, district_col, cost_col = st.columns([3, 2, 1])
        with measure_col:
            measure_id = st.selectbox(
                f"Мероприятие {index + 1}", list(CATALOG), key=measure_key,
                format_func=lambda code: f"{code} — {CATALOG[code]['name']}",
            )
        measure = CATALOG[measure_id]
        with district_col:
            if measure["scope"] == "city":
                st.caption("Территория")
                st.write("Весь город")
                district_id = None
            else:
                district_id = st.selectbox(
                    f"Территория {index + 1}", list(DISTRICTS),
                    key=district_key, format_func=DISTRICTS.get,
                )
        with cost_col:
            st.metric("Стоимость", money(measure["cost"]))
        decisions.append({"measure_id": measure_id, "district_id": district_id})

    spent = sum(CATALOG[d["measure_id"]]["cost"] for d in decisions)
    remaining = BUDGET - spent
    budget_col, spent_col, remaining_col = st.columns(3)
    budget_col.metric("Бюджет", money(BUDGET))
    spent_col.metric("Потрачено", money(spent))
    remaining_col.metric("Осталось", money(remaining))
    st.progress(min(spent / BUDGET, 1.0))
    unique = len({d["measure_id"] for d in decisions}) == 5
    if not unique:
        st.warning("Выберите пять разных мероприятий.")
    if remaining < 0:
        st.error(f"Бюджет превышен на {money(-remaining)}. Измените набор мероприятий.")

    signature = tuple((d["measure_id"], d["district_id"]) for d in decisions)
    previous = st.session_state.get("evaluation")
    if previous and previous["signature"] != signature:
        st.session_state.pop("evaluation", None)

    if st.button("Оценить решения", type="primary", disabled=not unique or remaining < 0):
        st.session_state.pop("evaluation", None)
        try:
            with st.spinner("Оцениваем решения…"):
                result = calculate_plan(decisions)
                st.session_state["evaluation"] = {"signature": signature, "result": result}
        except ValueError as exc:
            st.error(str(exc))

    st.subheader("Результаты")
    evaluation = st.session_state.get("evaluation")
    if evaluation is None:
        st.caption("Нажмите «Оценить решения», чтобы увидеть Score и показатели до/после.")
        return
    result = evaluation["result"]
    score_col, critical_col = st.columns(2)
    score_col.metric("Итоговый Score", f"{result['score']:.2f}", delta=f"{result['score_delta']:+.2f}")
    critical_col.metric("Критических показателей после", result["critical_counts"]["after"])
    st.caption(f"Базовый Score: {result['base_score']:.2f}. Критических показателей до: {result['critical_counts']['before']}.")
    rows = [{
        "Район": row["district"], "Показатель": f"{row['metric_id']} — {row['metric']}",
        "До": row["before"], "После": row["after"], "Изменение": row["delta"],
        "Критический после": row["critical_after"],
    } for row in result["comparison"]]
    st.dataframe(rows, hide_index=True, width="stretch")
    st.subheader("AI-разбор")
    st.info("AI-разбор пока не подключён. Расчёт выполнен по формуле датасета.")


if __name__ == "__main__":
    main()
