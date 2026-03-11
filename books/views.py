import math
import xml.etree.ElementTree as et
from datetime import datetime, timedelta

import pandas as pd
import requests
from decouple import config
from django.shortcuts import render

GOODREADS_API_KEY = config('GOODREADS_API_KEY')
GOODREADS_USER_ID = config('GOODREADS_USER_ID')

HEADERS = {
    "User-Agent": "PostmanRuntime/7.37.3",
    "Accept": "*/*",
}


def fetch_shelf_page(shelf, page):
    url = (
        f"https://www.goodreads.com/review/list?v=2"
        f"&key={GOODREADS_API_KEY}&id={GOODREADS_USER_ID}"
        f"&shelf={shelf}&per_page=200&page={page}"
    )
    r = requests.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    return r.text


def parse_books(xml_text):
    root = et.fromstring(xml_text)
    rows = []
    for book in root.findall("./reviews/review/book"):
        rows.append({
            "title": book.find("title").text,
            "num_pages": book.find("num_pages").text,
            "average_rating": book.find("average_rating").text,
            "ratings_count": book.find("ratings_count").text,
            "link": book.find("link").text,
        })
    return rows


def build_df(rows):
    df = pd.DataFrame(rows, columns=["title", "num_pages", "average_rating", "ratings_count", "link"])
    df["num_pages"] = pd.to_numeric(df["num_pages"], errors="coerce")
    df["average_rating"] = pd.to_numeric(df["average_rating"], errors="coerce")
    df["ratings_count"] = pd.to_numeric(df["ratings_count"], errors="coerce")
    df["num_pages"].fillna(df["num_pages"].mean(), inplace=True)
    df["average_rating"].fillna(df["average_rating"].mean(), inplace=True)
    df["ratings_count"].fillna(df["ratings_count"].mean(), inplace=True)

    df["score"] = df.apply(
        lambda r: (5 * r.average_rating / 10) + 2.5 * (1 - math.exp(-r.ratings_count / 720000)),
        axis=1,
    )
    df["score_per_page"] = df.apply(
        lambda r: (0.5 * r.average_rating)
        + 1.25 * (1 - math.exp(-r.ratings_count / 720000))
        + 1.25 * (1 - math.exp(-(300 / (1 + r.num_pages)))),
        axis=1,
    )
    return df.drop_duplicates(subset=["title"])


def get_shelf(shelf, max_pages=18):
    rows = []
    for page in range(1, max_pages + 1):
        try:
            xml = fetch_shelf_page(shelf, page)
            new_rows = parse_books(xml)
            if not new_rows:
                break
            rows.extend(new_rows)
        except Exception:
            break
    return build_df(rows)


def lista(request):
    df = get_shelf("to-read").sort_values("score", ascending=False)
    return render(request, "books/lista.html", {
        "books": df.to_dict("records"),
        "sort": "score",
        "active_tab": "rating",
    })


def lista_per_page(request):
    df = get_shelf("to-read").sort_values("score_per_page", ascending=False)
    return render(request, "books/lista.html", {
        "books": df.to_dict("records"),
        "sort": "score_per_page",
        "active_tab": "per_page",
    })


def lista_own_paper(request):
    df = get_shelf("own-paper", max_pages=3).sort_values("score_per_page", ascending=False)
    return render(request, "books/lista.html", {
        "books": df.to_dict("records"),
        "sort": "score_per_page",
        "active_tab": "own_paper",
    })


def plan(request):
    today = datetime.now()
    end_date = datetime(today.year, 12, 31, 23, 59)

    books_read = int(request.GET.get("books_read", 2))
    goal = int(request.GET.get("goal", 24))
    current_pages = int(request.GET.get("current_pages", 0))
    pages_read = int(request.GET.get("pages_read", 0))

    books_remaining = goal - books_read
    days_remaining = (end_date - today).days
    days_per_book = days_remaining / books_remaining if books_remaining > 0 else 0

    schedule = []
    date = today
    for i in range(books_remaining):
        schedule.append({
            "book_num": books_read + i + 1,
            "deadline": (date + timedelta(days=days_per_book)).strftime("%d-%m-%Y"),
        })
        date += timedelta(days=days_per_book)

    pages_per_day = None
    if current_pages > 0 and days_per_book > 0:
        pages_per_day = round((current_pages - pages_read) / days_per_book, 1)

    pct_per_day = None
    if current_pages > 0 and days_per_book > 0:
        pct_per_day = round(((current_pages - pages_read) / current_pages) / days_per_book * 100, 1)

    return render(request, "books/plan.html", {
        "active_tab": "plan",
        "books_read": books_read,
        "goal": goal,
        "books_remaining": books_remaining,
        "days_remaining": days_remaining,
        "days_per_book": round(days_per_book, 1),
        "schedule": schedule,
        "current_pages": current_pages,
        "pages_read": pages_read,
        "pages_per_day": pages_per_day,
        "pct_per_day": pct_per_day,
    })
