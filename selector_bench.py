"""Re-run of the article's selector benchmark: lxml XPath vs lxml CSS vs BS4 CSS.

Dataset: synthetic e-commerce page, product cards with nested spans plus noise
markup, sized to ~5 MB (the article's stated dataset size). Each engine runs the
same logical query 200 times against a tree parsed once. Reported per engine:
median, P95, min per-query duration (ms), stddev (jitter), and items/sec
(matched elements per query divided by median duration), matching the
published table's columns.

Writes results/selector_bench_results.json.
"""
import json
import pathlib
import statistics
import sys
import time

from bs4 import BeautifulSoup
from lxml import html

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = pathlib.Path(__file__).resolve().parent
(HERE / "results").mkdir(exist_ok=True)
MAX_RUNS = 200      # per engine
TIME_BUDGET = 30.0  # seconds per engine: stop after this much measured time
MIN_RUNS = 10

card = ('<div class="product-card"><h3 class="title">Item {i}</h3>'
        '<div class="meta"><span class="sku">SKU-{i}</span>'
        '<span class="price">${p}.99</span></div>'
        '<p class="desc">' + 'lorem ipsum dolor sit amet ' * 8 + '</p></div>')
noise = '<div class="banner"><ul>' + ''.join(f'<li><a href="/l{j}">link {j}</a></li>' for j in range(20)) + '</ul></div>'
parts = ['<html><body>']
size = len(parts[0])
i = 0
import os
TARGET = int(float(os.environ.get("SIZE_MB", "5")) * 1_000_000)
while size < TARGET:
    piece = card.format(i=i, p=10 + i % 90)
    parts.append(piece)
    size += len(piece)
    if i % 10 == 0:
        parts.append(noise)
        size += len(noise)
    i += 1
parts.append('</body></html>')
doc = ''.join(parts)
print(f"dataset: {len(doc)/1e6:.1f} MB, {i} product cards")

tree = html.fromstring(doc)
soup = BeautifulSoup(doc, "lxml")

engines = {
    "lxml XPath, nested // (article's query)": lambda: tree.xpath('//div[@class="product-card"]//span[@class="price"]'),
    "lxml XPath, direct path": lambda: tree.xpath('//div[@class="product-card"]/div/span[@class="price"]'),
    "lxml CSS (cssselect)": lambda: tree.cssselect('div.product-card span.price'),
    "lxml CSS, direct path": lambda: tree.cssselect('div.product-card > div.meta > span.price'),
    "BS4 CSS (soupsieve)": lambda: soup.select('div.product-card span.price'),
    "BS4 CSS, direct path": lambda: soup.select('div.product-card > div.meta > span.price'),
}

results = {}
for name, fn in engines.items():
    n_items = len(fn())  # warmup + item count
    times = []
    spent = 0.0
    while len(times) < MAX_RUNS and (spent < TIME_BUDGET or len(times) < MIN_RUNS):
        t0 = time.perf_counter()
        fn()
        dt = (time.perf_counter() - t0) * 1000
        times.append(dt)
        spent += dt / 1000
    runs = len(times)
    med = statistics.median(times)
    results[name] = {
        "median_ms": round(med, 3),
        "p95_ms": round(sorted(times)[int(len(times) * 0.95)], 3),
        "min_ms": round(min(times), 3),
        "stddev": round(statistics.stdev(times), 3),
        "runs": runs,
        "items_per_query": n_items,
        "items_per_sec": round(n_items / (med / 1000), 1),
    }
    print(name, results[name])

import platform
from lxml import etree
out = {"python": platform.python_version(),
       "lxml": etree.__version__, "libxml2": ".".join(map(str, etree.LIBXML_VERSION)),
       "policy": f"up to {MAX_RUNS} runs or {TIME_BUDGET}s per engine, min {MIN_RUNS}",
       "dataset_mb": round(len(doc)/1e6, 1), "cards": i, "results": results}
(HERE / "results" / f"selector_bench_results{'_1mb' if TARGET < 5_000_000 else ''}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
print("saved to results/")
