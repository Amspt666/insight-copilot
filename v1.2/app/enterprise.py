"""Enterprise contracts used by the v1.2 demo.

The lineage CSV is the authoritative relationship input for Join Planner. Model
output can propose business concepts, but it cannot create or override an edge.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from . import config


def load_enterprise_config() -> dict:
    return json.loads(config.ENTERPRISE_CONFIG_PATH.read_text(encoding="utf-8"))


def load_lineage() -> list[dict]:
    with config.LINEAGE_PATH.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    required = {"lineage_id", "upstream_object", "downstream_object", "join_key", "cardinality", "approval_state"}
    if not rows or not required.issubset(rows[0]):
        raise ValueError("企业血缘输入缺少必需列")
    return [row for row in rows if row.get("approval_state") == "approved"]


def metadata_for(metric: str, catalog: dict) -> dict:
    definition = catalog["metrics"][metric]
    tables = definition["tables"]
    lineage = [edge for edge in load_lineage()
               if edge["upstream_object"] in tables and edge["downstream_object"] in tables]
    return {
        "metric": definition,
        "tables": {name: catalog["tables"][name] for name in tables},
        "lineage_snapshot": load_enterprise_config()["lineage_snapshot"],
        "lineage_ids": [edge["lineage_id"] for edge in lineage],
        "lineage": lineage,
    }


def build_join_plan(metric: str, catalog: dict) -> dict:
    metadata = metadata_for(metric, catalog)
    tables = metadata["tables"]
    lineage = metadata["lineage"]
    required_pairs = {("BSEG", "BKPF"), ("BSEG", "KNA1"), ("BSEG", "T001")}
    if metric != "receipts":
        required_pairs.add(("BSEG", "ZAR_APPLICATION"))
    available = {(edge["upstream_object"], edge["downstream_object"]) for edge in lineage}
    missing = sorted(required_pairs - available)
    if missing:
        raise ValueError(f"权威血缘缺少允许的关联路径：{missing}")
    application_edge = next((edge for edge in lineage if edge["downstream_object"] == "ZAR_APPLICATION"), None)
    return {
        "status": "passed",
        "metric": metric,
        "tables": list(tables),
        "lineage_snapshot": metadata["lineage_snapshot"],
        "lineage_ids": metadata["lineage_ids"],
        "joins": [
            {"left": "BSEG", "right": "BKPF", "keys": "MANDT+BUKRS+GJAHR+BELNR", "cardinality": "N:1"},
            {"left": "BSEG", "right": "KNA1", "keys": "MANDT+KUNNR", "cardinality": "N:1"},
            {"left": "BSEG", "right": "T001", "keys": "MANDT+BUKRS", "cardinality": "N:1"},
        ] + ([] if metric == "receipts" else [{
            "left": "BSEG", "right": "ZAR_APPLICATION",
            "keys": application_edge["join_key"], "cardinality": application_edge["cardinality"],
            "pre_aggregate": application_edge["transformation_expression"] == "aggregate_before_join",
        }]),
        "grain": "document-item before application aggregation; final output at requested dimension",
        "warnings": ["ZAR_APPLICATION is 1:N and must be aggregated by invoice item before joining."] if metric != "receipts" else [],
    }
