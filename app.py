import csv
import io
import os
import threading
import webbrowser
from datetime import datetime

from flask import Flask, Response, flash, redirect, render_template, request, url_for

from database import (
    clear_events,
    get_setting,
    init_db,
    list_cards,
    list_first_arrivals,
    list_late_records,
    recent_passages,
    register_passage,
    seed_demo_data,
    set_setting,
)


app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-only-change-me")


def format_delay(minutes):
    if minutes <= 0:
        return "вовремя"
    days, remainder = divmod(minutes, 24 * 60)
    hours, remaining_minutes = divmod(remainder, 60)
    if days:
        return f"+{days} д. {hours} ч. {remaining_minutes} мин."
    if hours:
        return f"+{hours} ч. {remaining_minutes} мин."
    return f"+{remaining_minutes} мин."


app.add_template_filter(format_delay, "delay")


@app.route("/", methods=["GET"])
def index():
    selected_date = request.args.get("date", "")
    return render_template(
        "index.html",
        cards=list_cards(),
        passages=recent_passages(),
        late_records=list_late_records(selected_date or None),
        lesson_start=get_setting("lesson_start"),
        selected_date=selected_date,
        now=datetime.now().strftime("%Y-%m-%dT%H:%M"),
    )


@app.route("/passage", methods=["POST"])
def passage():
    try:
        register_passage(request.form["card_code"], request.form["passed_at"])
        flash("Проход зарегистрирован.", "success")
    except (KeyError, ValueError) as error:
        flash(str(error), "error")
    return redirect(url_for("index"))


@app.route("/settings", methods=["POST"])
def settings():
    lesson_start = request.form.get("lesson_start", "")
    try:
        datetime.strptime(lesson_start, "%H:%M")
    except ValueError:
        flash("Укажите корректное время начала пары.", "error")
    else:
        set_setting("lesson_start", lesson_start)
        flash("Время начала пары сохранено.", "success")
    return redirect(url_for("index"))


@app.route("/clear", methods=["POST"])
def clear():
    clear_events()
    flash("Учебные проходы и журнал очищены.", "success")
    return redirect(url_for("index"))


@app.route("/export.csv")
def export_csv():
    selected_date = request.args.get("date") or None
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output, delimiter=";")
    writer.writerow(
        [
            "Дата",
            "Время прохода",
            "ФИО",
            "Категория",
            "Группа",
            "Курс",
            "Статус",
            "Опоздание",
        ]
    )
    start_hour, start_minute = map(int, get_setting("lesson_start").split(":"))
    for row in list_first_arrivals(selected_date):
        moment = datetime.fromisoformat(row["passed_at"])
        start = moment.replace(
            hour=start_hour, minute=start_minute, second=0, microsecond=0
        )
        if row["role"] == "teacher":
            category = "Преподаватель"
            status = "Прошёл"
            delay = "—"
        elif row["course"] not in (1, 2):
            category = "Студент"
            status = "Прошёл"
            delay = "—"
        else:
            category = "Студент"
            minutes_late = int((moment - start).total_seconds() // 60)
            status = "Опоздал" if minutes_late > 0 else "Вовремя"
            delay = format_delay(minutes_late) if minutes_late > 0 else "—"
        writer.writerow(
            [
                row["arrival_date"],
                row["passed_at"][11:16],
                row["full_name"],
                category,
                row["group_name"] or "—",
                row["course"] or "—",
                status,
                delay,
            ]
        )
    return Response(
        output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=late_students.csv"},
    )


if __name__ == "__main__":
    init_db()
    seed_demo_data()
    threading.Timer(1.2, lambda: webbrowser.open("http://127.0.0.1:5051")).start()
    app.run(debug=False, port=5051)
