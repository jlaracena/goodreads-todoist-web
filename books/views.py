import time
import xml.etree.ElementTree as et
from datetime import datetime, timedelta
from math import ceil

import numpy as np
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

_cache: dict = {}
CACHE_TTL = 30 * 60  # 30 minutos


def fetch_shelf_page(shelf, page):
    url = (
        f"https://www.goodreads.com/review/list?v=2"
        f"&key={GOODREADS_API_KEY}&id={GOODREADS_USER_ID}"
        f"&shelf={shelf}&per_page=200&page={page}"
    )
    r = requests.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    return r.text


def parse_page(xml_text):
    """Devuelve (rows, total_books) leyendo el atributo total del XML."""
    root = et.fromstring(xml_text)
    reviews = root.find("reviews")
    total = int(reviews.attrib.get("total", 0)) if reviews is not None else 0
    rows = []
    for book in root.findall("./reviews/review/book"):
        rows.append({
            "title": book.find("title").text,
            "num_pages": book.find("num_pages").text,
            "average_rating": book.find("average_rating").text,
            "ratings_count": book.find("ratings_count").text,
            "link": book.find("link").text,
        })
    return rows, total


def build_df(rows):
    df = pd.DataFrame(rows, columns=["title", "num_pages", "average_rating", "ratings_count", "link"])
    for col in ["num_pages", "average_rating", "ratings_count"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
        df[col] = df[col].fillna(df[col].mean())

    df["score"] = (
        (5 * df["average_rating"] / 10)
        + 2.5 * (1 - np.exp(-df["ratings_count"] / 720000))
    )
    df["score_per_page"] = (
        0.5 * df["average_rating"]
        + 1.25 * (1 - np.exp(-df["ratings_count"] / 720000))
        + 1.25 * (1 - np.exp(-(300 / (1 + df["num_pages"]))))
    )

    # Normalizar score a porcentaje para la barra visual (relativo al máximo del shelf)
    df["score_pct"] = (df["score"] / df["score"].max() * 100).round(0).astype(int)

    return df.drop_duplicates(subset=["title"])


def get_shelf(shelf):
    if shelf in _cache:
        ts, data = _cache[shelf]
        if time.time() - ts < CACHE_TTL:
            return data

    # Primera página: obtener libros y total real del shelf
    first_rows, total = parse_page(fetch_shelf_page(shelf, 1))
    rows = first_rows

    total_pages = ceil(total / 200)
    for page in range(2, total_pages + 1):
        try:
            new_rows, _ = parse_page(fetch_shelf_page(shelf, page))
            rows.extend(new_rows)
        except Exception:
            break

    result = build_df(rows)
    _cache[shelf] = (time.time(), result)
    return result


def lista(request):
    df = get_shelf("to-read").sort_values("score", ascending=False)
    return render(request, "books/lista.html", {
        "books": df.to_dict("records"),
        "active_tab": "rating",
    })


def lista_per_page(request):
    df = get_shelf("to-read").sort_values("score_per_page", ascending=False)
    return render(request, "books/lista.html", {
        "books": df.to_dict("records"),
        "active_tab": "per_page",
    })


def lista_own_paper(request):
    df = get_shelf("own-paper").sort_values("score_per_page", ascending=False)
    return render(request, "books/lista.html", {
        "books": df.to_dict("records"),
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
        date += timedelta(days=days_per_book)
        schedule.append({
            "book_num": books_read + i + 1,
            "deadline": date.strftime("%d-%m-%Y"),
        })

    pages_per_day = pct_per_day = None
    if current_pages > 0 and days_per_book > 0:
        pages_remaining = current_pages - pages_read
        pages_per_day = round(pages_remaining / days_per_book, 1)
        pct_per_day = round(pages_remaining / current_pages / days_per_book * 100, 1)

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
