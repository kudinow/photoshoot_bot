#!/usr/bin/env python3
"""Генератор данных для дашборда. Читает SQLite → пишет data.json."""

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

# Пути
_PROD_DIR = Path("/opt/photoshoot_ai")
_LOCAL_DIR = Path(__file__).parent.parent

if _PROD_DIR.exists():
    DB_PATH = _PROD_DIR / "user_data.db"
    OUTPUT_PATH = Path("/var/www/landing/dash/data.json")
else:
    DB_PATH = _LOCAL_DIR / "user_data.db"
    OUTPUT_PATH = _LOCAL_DIR / "dash" / "data.json"

# Стоимость генерации
COST_PER_GENERATION = 2.5  # рублей (2₽ API + 0.5₽ промпт)

PACKAGE_LABELS = {
    "pack_5": "5 генераций / 149 ₽",
    "pack_15": "15 генераций / 349 ₽",
    "pack_50": "50 генераций / 899 ₽",
}

STYLE_LABELS = {
    "business": "Деловой",
    "casual": "Кежуал",
    "creative": "Креативный",
}


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def query_summary(conn):
    """Сводные метрики"""
    total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    row = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM payments "
        "WHERE status = 'confirmed'"
    ).fetchone()
    total_revenue = row[0] / 100.0  # копейки → рубли

    paying_users = conn.execute(
        "SELECT COUNT(DISTINCT user_id) FROM payments "
        "WHERE status = 'confirmed'"
    ).fetchone()[0]

    # Всего генераций: из лога + из users.generations (для истории до лога)
    log_count = conn.execute(
        "SELECT COUNT(*) FROM generations_log"
    ).fetchone()[0]

    free_used = conn.execute(
        "SELECT COALESCE(SUM(generations), 0) FROM users"
    ).fetchone()[0]
    paid_sold = conn.execute(
        "SELECT COALESCE(SUM(credits), 0) FROM payments "
        "WHERE status = 'confirmed'"
    ).fetchone()[0]
    paid_remaining = conn.execute(
        "SELECT COALESCE(SUM(paid_credits), 0) FROM users"
    ).fetchone()[0]

    # Если лог пустой, считаем из users
    total_generations = log_count if log_count > 0 else (
        free_used + paid_sold - paid_remaining
    )

    total_cost = total_generations * COST_PER_GENERATION
    total_profit = total_revenue - total_cost

    conversion_rate = (
        round(paying_users / total_users * 100, 1) if total_users > 0 else 0
    )
    arpu = round(total_revenue / total_users, 1) if total_users > 0 else 0

    # Среднее генераций на юзера
    avg_generations = (
        round(total_generations / total_users, 1) if total_users > 0 else 0
    )

    return {
        "total_users": total_users,
        "paying_users": paying_users,
        "total_revenue": round(total_revenue, 2),
        "total_cost": round(total_cost, 2),
        "total_profit": round(total_profit, 2),
        "total_generations": total_generations,
        "conversion_rate": conversion_rate,
        "arpu": arpu,
        "avg_generations": avg_generations,
    }


def query_users_over_time(conn):
    """Новые пользователи по дням (накопительно)"""
    rows = conn.execute(
        "SELECT DATE(created_at) AS day, COUNT(*) AS cnt "
        "FROM users WHERE created_at IS NOT NULL "
        "GROUP BY DATE(created_at) ORDER BY day"
    ).fetchall()

    labels = []
    daily = []
    cumulative = []
    total = 0
    for row in rows:
        labels.append(row["day"])
        daily.append(row["cnt"])
        total += row["cnt"]
        cumulative.append(total)

    return {"labels": labels, "daily": daily, "cumulative": cumulative}


def query_revenue_over_time(conn):
    """Выручка по дням (накопительно)"""
    rows = conn.execute(
        "SELECT DATE(confirmed_at) AS day, "
        "SUM(amount) / 100.0 AS revenue, "
        "COUNT(*) AS cnt "
        "FROM payments "
        "WHERE status = 'confirmed' AND confirmed_at IS NOT NULL "
        "GROUP BY DATE(confirmed_at) ORDER BY day"
    ).fetchall()

    labels = []
    daily_revenue = []
    daily_count = []
    cumulative_revenue = []
    cumulative_count = []
    total_rev = 0
    total_cnt = 0
    for row in rows:
        labels.append(row["day"])
        daily_revenue.append(round(row["revenue"], 2))
        daily_count.append(row["cnt"])
        total_rev += row["revenue"]
        total_cnt += row["cnt"]
        cumulative_revenue.append(round(total_rev, 2))
        cumulative_count.append(total_cnt)

    return {
        "labels": labels,
        "daily_revenue": daily_revenue,
        "daily_count": daily_count,
        "cumulative_revenue": cumulative_revenue,
        "cumulative_count": cumulative_count,
    }


def query_daily_generations(conn):
    """Генерации по дням (из лога)"""
    rows = conn.execute(
        "SELECT DATE(created_at) AS day, COUNT(*) AS cnt "
        "FROM generations_log "
        "GROUP BY DATE(created_at) ORDER BY day"
    ).fetchall()

    labels = [row["day"] for row in rows]
    counts = [row["cnt"] for row in rows]
    return {"labels": labels, "counts": counts}


def query_packages(conn):
    """Популярность пакетов"""
    rows = conn.execute(
        "SELECT package_id, COUNT(*) AS cnt, "
        "SUM(amount) / 100.0 AS revenue "
        "FROM payments WHERE status = 'confirmed' "
        "GROUP BY package_id ORDER BY cnt DESC"
    ).fetchall()

    return [
        {
            "package_id": row["package_id"],
            "label": PACKAGE_LABELS.get(row["package_id"], row["package_id"]),
            "count": row["cnt"],
            "revenue": round(row["revenue"], 2),
        }
        for row in rows
    ]


def query_sources(conn):
    """Источники трафика"""
    rows = conn.execute(
        "SELECT source, COUNT(*) AS cnt "
        "FROM referrals GROUP BY source ORDER BY cnt DESC"
    ).fetchall()

    return [{"source": row["source"], "count": row["cnt"]} for row in rows]


def query_styles(conn):
    """Популярность стилей"""
    rows = conn.execute(
        "SELECT style, COUNT(*) AS cnt "
        "FROM generations_log WHERE style IS NOT NULL "
        "GROUP BY style ORDER BY cnt DESC"
    ).fetchall()

    return [
        {
            "style": row["style"],
            "label": STYLE_LABELS.get(row["style"], row["style"]),
            "count": row["cnt"],
        }
        for row in rows
    ]


def query_retention(conn):
    """Retention D1/D7/D30"""
    rows = conn.execute("""
        WITH first_gen AS (
            SELECT user_id, MIN(DATE(created_at)) AS first_day
            FROM generations_log
            GROUP BY user_id
        ),
        gen_days AS (
            SELECT DISTINCT user_id, DATE(created_at) AS gen_day
            FROM generations_log
        )
        SELECT
            fg.user_id,
            fg.first_day,
            CASE WHEN EXISTS (
                SELECT 1 FROM gen_days gd
                WHERE gd.user_id = fg.user_id
                AND gd.gen_day = DATE(fg.first_day, '+1 day')
            ) THEN 1 ELSE 0 END AS d1,
            CASE WHEN EXISTS (
                SELECT 1 FROM gen_days gd
                WHERE gd.user_id = fg.user_id
                AND gd.gen_day BETWEEN DATE(fg.first_day, '+1 day')
                    AND DATE(fg.first_day, '+7 days')
            ) THEN 1 ELSE 0 END AS d7,
            CASE WHEN EXISTS (
                SELECT 1 FROM gen_days gd
                WHERE gd.user_id = fg.user_id
                AND gd.gen_day BETWEEN DATE(fg.first_day, '+1 day')
                    AND DATE(fg.first_day, '+30 days')
            ) THEN 1 ELSE 0 END AS d30
        FROM first_gen fg
    """).fetchall()

    today = datetime.now().strftime("%Y-%m-%d")

    eligible_d1 = sum(
        1 for r in rows
        if r["first_day"] <= (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    )
    eligible_d7 = sum(
        1 for r in rows
        if r["first_day"] <= (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    )
    eligible_d30 = sum(
        1 for r in rows
        if r["first_day"] <= (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    )

    retained_d1 = sum(
        r["d1"] for r in rows
        if r["first_day"] <= (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    )
    retained_d7 = sum(
        r["d7"] for r in rows
        if r["first_day"] <= (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    )
    retained_d30 = sum(
        r["d30"] for r in rows
        if r["first_day"] <= (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    )

    return {
        "d1": round(retained_d1 / eligible_d1 * 100, 1) if eligible_d1 > 0 else 0,
        "d7": round(retained_d7 / eligible_d7 * 100, 1) if eligible_d7 > 0 else 0,
        "d30": round(retained_d30 / eligible_d30 * 100, 1) if eligible_d30 > 0 else 0,
        "eligible_d1": eligible_d1,
        "eligible_d7": eligible_d7,
        "eligible_d30": eligible_d30,
    }


def main():
    conn = get_conn()

    data = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "summary": query_summary(conn),
        "users_over_time": query_users_over_time(conn),
        "revenue_over_time": query_revenue_over_time(conn),
        "daily_generations": query_daily_generations(conn),
        "package_popularity": query_packages(conn),
        "traffic_sources": query_sources(conn),
        "style_popularity": query_styles(conn),
        "retention": query_retention(conn),
    }

    conn.close()

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Data written to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
