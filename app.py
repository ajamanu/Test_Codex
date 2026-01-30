from __future__ import annotations

import io
import uuid
from dataclasses import dataclass
from typing import Dict, List

import pandas as pd
from difflib import SequenceMatcher
from flask import Flask, render_template, request, send_file

app = Flask(__name__)
app.secret_key = "dev-secret-key"

SIMILARITY_THRESHOLD = 0.85


@dataclass
class SimilarGroup:
    group_id: str
    indices: List[int]


@dataclass
class UploadState:
    dataframe: pd.DataFrame
    groups: List[SimilarGroup]


STATE_STORE: Dict[str, UploadState] = {}


class DisjointSet:
    def __init__(self, size: int) -> None:
        self.parents = list(range(size))
        self.ranks = [0] * size

    def find(self, item: int) -> int:
        if self.parents[item] != item:
            self.parents[item] = self.find(self.parents[item])
        return self.parents[item]

    def union(self, left: int, right: int) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return
        if self.ranks[left_root] < self.ranks[right_root]:
            self.parents[left_root] = right_root
        elif self.ranks[left_root] > self.ranks[right_root]:
            self.parents[right_root] = left_root
        else:
            self.parents[right_root] = left_root
            self.ranks[left_root] += 1


def build_similarity_groups(descriptions: List[str]) -> List[SimilarGroup]:
    matcher = SequenceMatcher
    count = len(descriptions)
    disjoint = DisjointSet(count)

    for i in range(count):
        for j in range(i + 1, count):
            score = matcher(None, descriptions[i], descriptions[j]).ratio()
            if score >= SIMILARITY_THRESHOLD:
                disjoint.union(i, j)

    grouped: Dict[int, List[int]] = {}
    for idx in range(count):
        root = disjoint.find(idx)
        grouped.setdefault(root, []).append(idx)

    groups = []
    for group_indices in grouped.values():
        if len(group_indices) > 1:
            group_id = str(uuid.uuid4())
            groups.append(SimilarGroup(group_id=group_id, indices=group_indices))

    return groups


def normalize_columns(dataframe: pd.DataFrame) -> pd.DataFrame:
    dataframe = dataframe.copy()
    dataframe.columns = [col.strip().lower() for col in dataframe.columns]
    return dataframe


@app.route("/", methods=["GET"])
def upload_form() -> str:
    return render_template("upload.html")


@app.route("/upload", methods=["POST"])
def upload_file():
    uploaded_file = request.files.get("inventory_file")
    if not uploaded_file:
        return render_template("upload.html", error="Please choose an Excel file to upload.")

    try:
        dataframe = pd.read_excel(uploaded_file)
    except Exception as exc:  # noqa: BLE001 - provide user feedback
        return render_template(
            "upload.html",
            error=f"Unable to read the Excel file: {exc}",
        )

    dataframe = normalize_columns(dataframe)
    if "description" not in dataframe.columns or "inventory_id" not in dataframe.columns:
        return render_template(
            "upload.html",
            error="Excel file must include 'description' and 'inventory_id' columns.",
        )

    descriptions = dataframe["description"].fillna("").astype(str).tolist()
    groups = build_similarity_groups(descriptions)

    session_id = str(uuid.uuid4())
    STATE_STORE[session_id] = UploadState(dataframe=dataframe, groups=groups)

    return render_template(
        "review.html",
        session_id=session_id,
        groups=groups,
        dataframe=dataframe,
        threshold=SIMILARITY_THRESHOLD,
    )


@app.route("/finalize", methods=["POST"])
def finalize_merge():
    session_id = request.form.get("session_id")
    if not session_id or session_id not in STATE_STORE:
        return render_template(
            "upload.html",
            error="Session expired. Please upload the file again.",
        )

    state = STATE_STORE[session_id]
    dataframe = state.dataframe.copy()
    dataframe["merged_inventory_id"] = dataframe["inventory_id"].astype(str)

    for group in state.groups:
        decision = request.form.get(f"decision_{group.group_id}", "merge")
        if decision != "merge":
            continue

        group_rows = dataframe.iloc[group.indices]
        merged_id = group_rows["inventory_id"].astype(str).min()
        dataframe.loc[group_rows.index, "merged_inventory_id"] = merged_id

    output = io.BytesIO()
    dataframe.to_excel(output, index=False)
    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name="merged_inventory.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
