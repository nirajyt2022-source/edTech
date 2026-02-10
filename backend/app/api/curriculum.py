import json
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/curriculum", tags=["curriculum"])

# Load curriculum canon at import time (cached)
_canon_path = Path(__file__).parent.parent / "data" / "curriculum_canon.json"
with open(_canon_path, "r") as f:
    _canon = json.load(f)

_grades_data: dict[int, dict] = {}
for g in _canon["grades"]:
    _grades_data[g["grade"]] = g


@router.get("/grades")
async def list_grades():
    """List all supported grades."""
    return {"grades": sorted(_grades_data.keys())}


@router.get("/subjects/{grade}")
async def list_subjects(
    grade: int,
    region: str = Query("India", pattern="^(India|UAE)$"),
    include_reinforcement: bool = Query(False),
):
    """List subjects for a grade, filtered by region.

    Global subjects always included. Region-specific subjects filtered:
    India users don't see UAE-only, UAE users don't see India-only.
    """
    grade_data = _grades_data.get(grade)
    if not grade_data:
        raise HTTPException(status_code=404, detail=f"Grade {grade} not found")

    subjects = []
    for subj in grade_data["subjects"]:
        # Filter by depth
        if subj["depth"] == "reinforcement" and not include_reinforcement:
            continue

        # Filter by region
        subj_region = subj["region"]
        if subj_region == "Global":
            pass  # always include
        elif subj_region == region:
            pass  # match
        else:
            continue  # skip (e.g. India-only for UAE user)

        subjects.append({
            "name": subj["name"],
            "region": subj["region"],
            "source": subj.get("source"),
            "skills": subj["skills"],
            "logic_tags": subj["logic_tags"],
            "depth": subj["depth"],
        })

    return {"grade": grade, "region": region, "subjects": subjects}


@router.get("/{grade}/{subject}")
async def get_subject_detail(
    grade: int,
    subject: str,
    region: str = Query("India", pattern="^(India|UAE)$"),
):
    """Get detailed skills and logic tags for a specific grade+subject."""
    grade_data = _grades_data.get(grade)
    if not grade_data:
        raise HTTPException(status_code=404, detail=f"Grade {grade} not found")

    for subj in grade_data["subjects"]:
        if subj["name"].lower() == subject.lower():
            # Verify region access
            subj_region = subj["region"]
            if subj_region != "Global" and subj_region != region:
                raise HTTPException(
                    status_code=403,
                    detail=f"{subject} is not available in {region} region"
                )
            return {
                "grade": grade,
                "subject": subj["name"],
                "region": subj["region"],
                "source": subj.get("source"),
                "skills": subj["skills"],
                "logic_tags": subj["logic_tags"],
                "depth": subj["depth"],
                "stage": grade_data["stage"],
            }

    raise HTTPException(status_code=404, detail=f"Subject '{subject}' not found for grade {grade}")
