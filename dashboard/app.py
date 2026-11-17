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
    audit_rows, conflict_rows, memory_rows, summary_cards, tombstone_rows,
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
    # One real tombstone for the Tombstones tab: the offsite moved.
    old_venue, _ = mem.write("planner", "team offsite is Lahore", "shared",
                             "user")
    mem.supersede("planner", old_venue.record_id, "team offsite is Karachi",
                  "user", reason="venue changed by organiser")
    return mem


if "mem" not in st.session_state:
    st.session_state.mem = _seed()
mem: GovernedMemory = st.session_state.mem

tab_view, tab_write, tab_search, tab_tombstones, tab_audit = st.tabs(
    ["Consolidated view", "Write a memory", "Search",
     "Tombstones — what we used to believe", "Audit log"])

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
        st.dataframe(conflicts, width="stretch")
    else:
        st.success("No open conflicts.")
    st.subheader("Active memories (newest first)")
    st.dataframe(memory_rows(view.active), width="stretch")
    st.subheader("Superseded — still readable, with their replacement")
    st.dataframe(memory_rows(view.superseded), width="stretch")

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
                width="stretch")
        else:
            st.info("No matching active memories.")

with tab_tombstones:
    stones = mem.tombstones("admin", "shared")
    st.metric("Tombstones in shared", len(stones))
    st.caption("Superseded records stay queryable as history — with the "
               "record that replaced them, the reason, and the time. "
               "Confidence decays with a 24-hour half-life, so an old "
               "belief weighs less the longer it has been dead. Live "
               "queries never return a tombstone as a current fact.")
    if stones:
        st.dataframe(tombstone_rows(stones), width="stretch")
        st.subheader("Full chain — what we believed, when, and why")
        choice = st.selectbox(
            "Pick a tombstone to see its whole supersession chain",
            [t.record_id for t in stones],
            format_func=lambda rid: next(
                (t.text for t in stones if t.record_id == rid), rid))
        chain = mem.tombstone_history("admin", choice)
        st.dataframe(tombstone_rows(chain), width="stretch")
    else:
        st.info("No tombstones yet — supersede a memory to create one.")

with tab_audit:
    st.dataframe(audit_rows(mem.audit_log()), width="stretch")
