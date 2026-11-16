"""Streamlit dashboard for governed shared memory.

Runs the real pipeline: the demo scenario writes into a live
``GovernedMemory`` (in-memory), and every tab reads from it — the
consolidated view, the open conflicts, the audit log, and BM25 search
are all computed from the same objects the tests exercise.

Run: ``streamlit run dashboard/app.py``
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402

from dashboard.helpers import (  # noqa: E402
    audit_rows, conflict_rows, memory_rows, summary_cards,
)
from governed_shared_memory.access import Agent  # noqa: E402
from governed_shared_memory.consolidation import consolidate  # noqa: E402
from governed_shared_memory.memory import GovernedMemory  # noqa: E402

st.set_page_config(page_title="Governed Shared Memory", layout="wide")
st.title("Governed Shared Memory")
st.caption("Multi-agent memory with access control, contradiction "
           "detection, provenance, and explicit supersession — offline.")

AGENTS = [Agent("planner", "writer"), Agent("researcher", "writer"),
          Agent("critic", "writer"), Agent("admin", "admin")]


def _seed() -> GovernedMemory:
    mem = GovernedMemory()
    for agent in AGENTS:
        mem.register(agent)
    mem.write("planner", "project deadline is 12 January", "shared", "user")
    mem.write("researcher", "project deadline is 20 January", "shared",
              "agent:planner")
    mem.write("planner", "conference budget is $800", "shared", "user")
    mem.write("researcher", "workshop venue is Karachi", "shared",
              "tool:web")
    mem.write("planner", "planner private note: draft budget figures",
              "planner", "user")
    mem.write("critic", "saliency maps improved clinician trust", "shared",
              "tool:arxiv")
    mem.write("researcher", "saliency maps did not improve clinician trust",
              "shared", "tool:arxiv")
    return mem


if "mem" not in st.session_state:
    st.session_state.mem = _seed()
mem: GovernedMemory = st.session_state.mem

tab_view, tab_write, tab_search, tab_audit = st.tabs(
    ["Consolidated view", "Write a memory", "Search", "Audit log"])

with tab_view:
    view = consolidate(mem.store.list(namespace="shared", status=None),
                       "shared")
    cards = summary_cards(view)
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Active memories", cards["active"])
    col2.metric("Open conflicts", cards["open_conflicts"])
    col3.metric("Conflicted records", cards["conflicted_records"])
    col4.metric("Superseded", cards["superseded"])
    st.subheader("Open conflicts — surfaced, never silently resolved")
    conflicts = conflict_rows(view)
    if conflicts:
        st.dataframe(conflicts, use_container_width=True)
    else:
        st.success("No open conflicts.")
    st.subheader("Active memories (newest first)")
    st.dataframe(memory_rows(view.active), use_container_width=True)
    st.subheader("Superseded — still readable, with their replacement")
    st.dataframe(memory_rows(view.superseded), use_container_width=True)

with tab_write:
    with st.form("write"):
        agent = st.selectbox("Writer", ["planner", "researcher", "critic"])
        namespace = st.selectbox("Namespace", ["shared", "planner",
                                               "researcher", "critic"])
        text = st.text_input("Memory text",
                             "project deadline is 12 January")
        source = st.text_input("Source", "user")
        submitted = st.form_submit_button("Write memory")
    if submitted:
        try:
            record, conflicts = mem.write(agent, text, namespace, source)
            st.success(f"Wrote {record.record_id}")
            for conflict in conflicts:
                st.warning(f"Conflict [{conflict.kind}]: {conflict.reason}")
        except PermissionError as exc:
            st.error(f"Denied: {exc}")

with tab_search:
    query = st.text_input("Query", "project deadline")
    if st.button("Search shared memory"):
        results = mem.search("admin", query, "shared")
        if results:
            st.dataframe(
                [{"score": round(score, 3), "writer": r.writer,
                  "text": r.text, "status": r.status}
                 for r, score in results],
                use_container_width=True)
        else:
            st.info("No matching active memories.")

with tab_audit:
    st.dataframe(audit_rows(mem.audit_log()), use_container_width=True)
