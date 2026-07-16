import os

import httpx
import pandas as pd
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000")
# Render's `fromService ... property: host` injects a bare hostname with no scheme;
# prepend https:// so the httpx calls below have a valid absolute URL.
if not API_URL.startswith(("http://", "https://")):
    API_URL = "https://" + API_URL

st.set_page_config(page_title="Market Analysis Agent", page_icon="📊", layout="wide")
st.title("📊 E-commerce Market Analysis Agent")
st.caption("Enter a product; the agent scrapes price, analyzes sentiment and trend, "
           "then an LLM writes recommendations.")

with st.form("analyze"):
    col1, col2 = st.columns([3, 1])
    product = col1.text_input("Product", value="iPhone 15")
    marketplace = col2.text_input("Marketplace", value="amazon")
    submitted = st.form_submit_button("Run analysis", use_container_width=True)

if submitted:
    with st.spinner("Running the agent pipeline (plan → scrape → sentiment ∥ trend → synthesize)..."):
        try:
            resp = httpx.post(
                f"{API_URL}/analyze",
                json={"product": product, "marketplace": marketplace or None},
                timeout=120,
            )
            resp.raise_for_status()
            report = resp.json()
        except Exception as exc:  # noqa: BLE001
            st.error(f"Request failed: {exc}")
            st.stop()

    if report.get("warnings"):
        st.warning("Partial report — some tools degraded:\n\n" +
                   "\n".join(f"- {w}" for w in report["warnings"]))

    st.subheader("Executive summary")
    st.write(report["summary"])

    m1, m2, m3 = st.columns(3)
    m1.metric("Price", f"{report['price']['price']} {report['price']['currency']}",
              help=f"source: {report['price']['source']}")
    m2.metric("Sentiment (pos/total)",
              f"{report['sentiment']['positive']}/{report['sentiment']['total']}")
    m3.metric("Trend", report["trend"]["direction"],
              f"{report['trend']['price_change_pct']}%")

    st.subheader("Recommendations")
    for rec in report["recommendations"]:
        st.markdown(f"- {rec}")

    left, right = st.columns(2)
    with left:
        st.markdown("**Competitor prices**")
        comp = pd.DataFrame(report["competitors"])
        if not comp.empty:
            st.bar_chart(comp.set_index("name")["price"])
        st.markdown("**Sentiment breakdown**")
        s = report["sentiment"]
        st.bar_chart(pd.DataFrame(
            {"count": [s["positive"], s["neutral"], s["negative"]]},
            index=["positive", "neutral", "negative"],
        ))
    with right:
        st.markdown("**Price history**")
        ph = pd.DataFrame(report["trend"]["price_history"])
        if not ph.empty:
            st.line_chart(ph.set_index("month")["price"])
        st.markdown("**Popularity**")
        pop = pd.DataFrame(report["trend"]["popularity"])
        if not pop.empty:
            st.line_chart(pop.set_index("month")["value"])

    with st.expander("Raw report JSON"):
        st.json(report)
