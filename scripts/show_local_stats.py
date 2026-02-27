import sqlite3

con = sqlite3.connect("advuman_local.db")
cur = con.cursor()

print("events=", cur.execute("select count(1) from events").fetchone()[0])
print("weighted_scores=", cur.execute("select count(1) from weighted_scores").fetchone()[0])
print("snapshots=", cur.execute("select count(1) from index_snapshots").fetchone()[0])
print("lane_health=", cur.execute("select count(1) from lane_health").fetchone()[0])
print(
    "this_week_events=",
    cur.execute(
        "select count(1) from events where date_observed >= '2026-02-23' and date_observed <= '2026-02-27'"
    ).fetchone()[0],
)
print(
    "latest_health=",
    cur.execute(
        "select week_start, week_end, combined_total, health_status from lane_health order by id desc limit 1"
    ).fetchone(),
)

con.close()
