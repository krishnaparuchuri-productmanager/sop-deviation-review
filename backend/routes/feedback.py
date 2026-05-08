"""
routes/feedback.py — POST /api/feedback endpoint for the SOP Deviation Review Assistant.

Accepts a numeric rating (1 = thumbs up, -1 = thumbs down) tied to a specific trace,
an optional free-text comment, and an optional reviewer_correction field that captures
the reviewer's suggested correction when they disagree with the assessment.

All four fields are written to the `feedback` table.  The trace_id FK is enforced
at the DB level; an unknown trace_id returns 404.
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter()

# ---------------------------------------------------------------------------
# Resolve DB path relative to this file (backend/routes/feedback.py)
# ---------------------------------------------------------------------------
_DB_PATH = Path(__file__).resolve().parent.parent / "db" / "sop_assistant.db"


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class FeedbackRequest(BaseModel):
    """Body accepted by POST /api/feedback."""

    trace_id: str = Field(
        ...,
        description="UUID of the /api/review trace this feedback belongs to.",
    )
    rating: int = Field(
        ...,
        description="1 for thumbs up (agree), -1 for thumbs down (disagree).",
    )
    comment: str | None = Field(
        default=None,
        max_length=2000,
        description="Optional free-text note from the QA reviewer.",
    )
    reviewer_correction: str | None = Field(
        default=None,
        max_length=4000,
        description=(
            "Optional corrected assessment text supplied by the reviewer "
            "when rating = -1 (thumbs down)."
        ),
    )

    def validate_rating(self) -> None:
        """Raise ValueError if rating is not 1 or -1."""
        if self.rating not in (1, -1):
            raise ValueError("rating must be 1 (thumbs up) or -1 (thumbs down)")


class FeedbackResponse(BaseModel):
    """Returned after a successful feedback submission."""

    feedback_id:         str
    trace_id:            str
    rating:              int
    has_correction:      bool
    message:             str


# ---------------------------------------------------------------------------
# POST /api/feedback
# ---------------------------------------------------------------------------

@router.post(
    "/feedback",
    response_model=FeedbackResponse,
    summary="Submit feedback on a deviation review",
    description=(
        "Records a thumbs-up (1) or thumbs-down (-1) rating for a completed deviation "
        "review, along with an optional reviewer comment and optional corrected output. "
        "The trace_id must refer to an existing review trace."
    ),
    responses={
        200: {"description": "Feedback recorded"},
        400: {"description": "Invalid rating value (must be 1 or -1)"},
        404: {"description": "trace_id not found in the traces table"},
        500: {"description": "Database error"},
    },
)
def submit_feedback(body: FeedbackRequest) -> FeedbackResponse:
    """
    Write one feedback row to the database.

    Steps:
      1. Validate that rating is exactly 1 or -1.
      2. Verify the trace_id exists in the traces table.
      3. Insert a new feedback row with a fresh UUID and UTC timestamp.
      4. Return the feedback_id for client-side confirmation.
    """
    # 1. Validate rating value -----------------------------------------------
    if body.rating not in (1, -1):
        raise HTTPException(
            status_code=400,
            detail="rating must be 1 (thumbs up) or -1 (thumbs down).",
        )

    feedback_id = str(uuid.uuid4())
    created_at  = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        conn = sqlite3.connect(_DB_PATH)
        conn.execute("PRAGMA foreign_keys=ON;")
        try:
            # 2. Confirm trace exists ----------------------------------------
            row = conn.execute(
                "SELECT id FROM traces WHERE id = ?", (body.trace_id,)
            ).fetchone()

            if row is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"trace_id '{body.trace_id}' not found. "
                           "Submit a deviation review first.",
                )

            # 3. Insert feedback row -----------------------------------------
            with conn:
                conn.execute(
                    """
                    INSERT INTO feedback
                        (id, trace_id, rating, comment, reviewer_correction, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        feedback_id,
                        body.trace_id,
                        body.rating,
                        body.comment.strip() if body.comment else None,
                        body.reviewer_correction.strip() if body.reviewer_correction else None,
                        created_at,
                    ),
                )

        finally:
            conn.close()

    except HTTPException:
        raise                                   # re-raise 400/404 without wrapping
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Foreign-key constraint failed — trace_id not found: {exc}",
        ) from exc
    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Database error while saving feedback: {exc}",
        ) from exc

    return FeedbackResponse(
        feedback_id    = feedback_id,
        trace_id       = body.trace_id,
        rating         = body.rating,
        has_correction = bool(body.reviewer_correction),
        message        = "Feedback recorded. Thank you.",
    )


# ---------------------------------------------------------------------------
# GET /api/feedback
# ---------------------------------------------------------------------------

class FeedbackItem(BaseModel):
    """One feedback row joined with its parent trace."""

    feedback_id:         str
    trace_id:            str
    rating:              int           # 1 = thumbs up, -1 = thumbs down
    comment:             str | None
    reviewer_correction: str | None
    created_at:          str
    # Joined from traces
    user_input:          str | None    # deviation text the reviewer rated
    review_timestamp:    str | None    # when the review was originally run


class FeedbackListResponse(BaseModel):
    """Returned by GET /api/feedback."""

    count:    int
    feedback: list[FeedbackItem]


@router.get(
    "/feedback",
    response_model=FeedbackListResponse,
    summary="List all feedback records",
    description=(
        "Returns up to `limit` feedback records (default 50), newest first. "
        "Each item is joined with its parent trace so the deviation text is available "
        "for display in the Feedback Queue."
    ),
    responses={
        200: {"description": "Feedback records returned"},
        500: {"description": "Database error"},
    },
)
def list_feedback(
    limit: int = Query(default=50, ge=1, le=500,
                       description="Maximum number of records to return"),
) -> FeedbackListResponse:
    """
    Fetch feedback rows joined with trace user_input and timestamp.

    The LEFT JOIN means feedback rows are returned even if the parent
    trace has been deleted (user_input / review_timestamp will be None).
    """
    try:
        conn = sqlite3.connect(_DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT
                    f.id              AS feedback_id,
                    f.trace_id,
                    f.rating,
                    f.comment,
                    f.reviewer_correction,
                    f.created_at,
                    t.user_input      AS user_input,
                    t.timestamp       AS review_timestamp
                FROM   feedback f
                LEFT JOIN traces t ON t.id = f.trace_id
                ORDER  BY f.created_at DESC
                LIMIT  ?
                """,
                (limit,),
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail=f"Database error: {exc}") from exc

    items = [
        FeedbackItem(
            feedback_id         = r["feedback_id"],
            trace_id            = r["trace_id"],
            rating              = r["rating"],
            comment             = r["comment"],
            reviewer_correction = r["reviewer_correction"],
            created_at          = r["created_at"],
            user_input          = r["user_input"],
            review_timestamp    = r["review_timestamp"],
        )
        for r in rows
    ]

    return FeedbackListResponse(count=len(items), feedback=items)
