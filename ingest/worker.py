"""The scheduler. The web app NEVER calls CMC -- only this does.

Why the split: page loads stop depending on CMC being up, credits stay bounded,
and the site keeps working after your Startup tier expires on 30 Sep while judging
runs to 16 Oct.

APScheduler: https://apscheduler.readthedocs.io/en/3.x/
"""

# from apscheduler.schedulers.blocking import BlockingScheduler


# def refresh_universe():
#     """Hourly. listings() -> upsert tokens -> insert snapshots."""
#     ...


# def refresh_pairs():
#     """Hourly. One market_pairs() call per token.
#     ~500 tokens = ~500 calls = ~12k/day. Inside Startup tier, but measure it.
#     Stagger the calls; do not fire 500 requests in one burst."""
#     ...


# def recompute_impact():
#     """After each pairs refresh: venue_features -> Y -> max_position -> grade.
#     Diff against the previous grade to emit the DOWNGRADE FEED -- that feed is
#     what proves to a judge the system ran unattended for days."""
#     ...


# def daily_books():
#     """books.snapshot_all(). Ground truth accrues."""
#     ...


# if __name__ == "__main__":
#     s = BlockingScheduler()
#     s.add_job(refresh_universe, "interval", hours=1)
#     s.add_job(refresh_pairs,    "interval", hours=1)
#     s.add_job(recompute_impact, "interval", hours=1)
#     s.add_job(daily_books,      "interval", hours=24)
#     s.start()
