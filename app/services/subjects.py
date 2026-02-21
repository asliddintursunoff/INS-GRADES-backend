import io
import re
import pandas as pd
from uuid import uuid4
from fastapi import HTTPException, UploadFile
from pydantic import BaseModel, model_validator
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Major, StudentYear, Subject, SubjectMajorLink

ALLOWED_CONTENT_TYPES = ["text/csv", "application/vnd.ms-excel"]  # browsers sometimes send weird types
ALLOWED_EXTENSIONS = ["csv", "tsv"]

import io
import pandas as pd
from fastapi import HTTPException, UploadFile


def _read_csv_safe(upload_file: UploadFile) -> pd.DataFrame:
    upload_file.file.seek(0)
    raw = upload_file.file.read()

    # Detect Excel xlsx mistakenly uploaded
    if raw[:2] == b"PK":
        raise HTTPException(
            status_code=400,
            detail="You uploaded an Excel (.xlsx) file. Please export as CSV or TSV."
        )

    # Try common encodings
    for enc in ["utf-8", "utf-8-sig", "utf-16", "cp1252", "latin-1"]:
        try:
            text = raw.decode(enc, errors="replace")

            # 🔥 AUTO-DETECT delimiter
            df = pd.read_csv(
                io.StringIO(text),
                sep=None,          # auto detect , or \t
                engine="python",
                dtype=str,
                keep_default_na=False,
            )

            df.columns = df.columns.str.strip().str.lower()

            expected = {"name", "year", "major_type"}
            if not expected.issubset(set(df.columns)):
                continue

            df["name"] = df["name"].str.strip()
            df["year"] = df["year"].str.strip()
            df["major_type"] = df["major_type"].str.strip()

            df = df[df["name"] != ""]
            df = df[df["year"] != ""]

            return df

        except Exception:
            continue

    raise HTTPException(status_code=400, detail="Unable to parse file.")


# ---------- major_type parsing ----------
_SPLIT_RE = re.compile(r"[,\s;/|]+")

def parse_major_types(value: str) -> list[str]:
    """
    Input examples:
      "CSE ICE BUS LOG" -> ["CSE","ICE","BUS","LOG"]
      "BUS LOG"         -> ["BUS","LOG"]
      ""                -> []
      "CSE, ICE;BUS"    -> ["CSE","ICE","BUS"]
    """
    if value is None:
        return []
    value = str(value).strip()
    if not value or value.lower() in {"nan", "none"}:
        return []

    parts = [p.strip().upper() for p in _SPLIT_RE.split(value) if p.strip()]
    # unique while keeping order
    seen = set()
    out = []
    for p in parts:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


# ---------- Pydantic helper ----------
class SubjectBase(BaseModel):
    name: str
    short_name: str | None = None

    @model_validator(mode="after")
    def generate_short_name(self):
        if not self.short_name:
            words = self.name.replace("&", " ")
            initials = "".join(word[0] for word in words.split() if word)
            self.short_name = initials[:20]  # optional limit
        return self


# ---------- Service ----------
class SubjectService:
    def __init__(self, session: AsyncSession):
        self.session = session
        # simple caches to reduce DB hits
        self._year_cache: dict[str, StudentYear] = {}
        self._major_cache: dict[str, Major] = {}

    def _validate_upload(self, file: UploadFile):
        if not file.filename or "." not in file.filename:
            raise HTTPException(detail="File must have .csv/.tsv extension", status_code=400)

        ext = file.filename.rsplit(".", 1)[-1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(detail="Only CSV/TSV allowed", status_code=400)

        if file.content_type and file.content_type not in ALLOWED_CONTENT_TYPES:
            # don't hard fail because some browsers set odd types,
            # but if you want strict, uncomment below:
            # raise HTTPException(detail="Only CSV allowed", status_code=400)
            pass

    async def _get_or_create_year(self, year_name: str) -> StudentYear:
        year_name = year_name.strip().lower()
        if year_name in self._year_cache:
            return self._year_cache[year_name]

        stmt = await self.session.execute(
            select(StudentYear).where(StudentYear.year_name == year_name)
        )
        year = stmt.scalar_one_or_none()

        if not year:
            year = StudentYear(
                id=uuid4(),
                year_name=year_name,
                starting_year=0,
                graduation_year=0,
            )
            self.session.add(year)
            await self.session.flush()

        self._year_cache[year_name] = year
        return year

    async def _get_or_create_major(self, major_name: str) -> Major:
        major_name = major_name.strip().upper()
        if major_name in self._major_cache:
            return self._major_cache[major_name]

        stmt = await self.session.execute(
            select(Major).where(Major.major_name == major_name)
        )
        major = stmt.scalar_one_or_none()

        if not major:
            major = Major(id=uuid4(), major_name=major_name, major_full_name=None)
            self.session.add(major)
            await self.session.flush()

        self._major_cache[major_name] = major
        return major

    async def _set_subject_majors(self, subject_id, major_names: list[str]):
        """
        Makes DB links EXACTLY match major_names:
          - adds missing
          - removes extra
        """
        desired = set(major_names)

        # existing links
        existing_stmt = await self.session.execute(
            select(SubjectMajorLink).where(SubjectMajorLink.subject_id == subject_id)
        )
        existing_links = existing_stmt.scalars().all()

        existing_major_ids = {link.major_id for link in existing_links if link.major_id is not None}

        # map desired major names -> ids
        desired_major_ids = set()
        for mn in desired:
            major = await self._get_or_create_major(mn)
            desired_major_ids.add(major.id)

        # remove extra links
        to_remove = existing_major_ids - desired_major_ids
        if to_remove:
            await self.session.execute(
                delete(SubjectMajorLink).where(
                    SubjectMajorLink.subject_id == subject_id,
                    SubjectMajorLink.major_id.in_(to_remove),
                )
            )

        # add missing links
        to_add = desired_major_ids - existing_major_ids
        for major_id in to_add:
            self.session.add(
                SubjectMajorLink(
                    id=uuid4(),
                    subject_id=subject_id,
                    major_id=major_id,
                )
            )

    # -------- Replace everything from file (FULL RESET) --------
    async def replace_subjects_by_csv(self, file: UploadFile) -> str:
        self._validate_upload(file)
        df = _read_csv_safe(file)
        rows = df.to_dict(orient="records")

        try:
            # full reset (links first, then subjects)
            await self.session.execute(delete(SubjectMajorLink))
            await self.session.execute(delete(Subject))
            await self.session.commit()

            # clear caches after reset
            self._year_cache.clear()
            self._major_cache.clear()

            for row in rows:
                name = str(row["name"]).strip()
                year_name = str(row["year"]).strip()
                major_types = parse_major_types(row.get("major_type", ""))

                subject_data = SubjectBase(name=name)
                year = await self._get_or_create_year(year_name)

                subject = Subject(
                    id=uuid4(),
                    name=subject_data.name,
                    short_name=subject_data.short_name,
                    student_year_id=year.id,
                )
                self.session.add(subject)
                await self.session.flush()

                # create links (if major_types empty => no links)
                for m in major_types:
                    major = await self._get_or_create_major(m)
                    self.session.add(
                        SubjectMajorLink(
                            id=uuid4(),
                            major_id=major.id,
                            subject_id=subject.id,
                        )
                    )

            await self.session.commit()
            return "Subjects fully replaced from file"

        except Exception as e:
            await self.session.rollback()
            raise HTTPException(detail=str(e), status_code=500)

    # -------- Update / Upsert from file (SAFE UPDATE) --------
    async def update_subjects_by_csv(self, file: UploadFile) -> str:
        self._validate_upload(file)
        df = _read_csv_safe(file)
        rows = df.to_dict(orient="records")

        try:
            for row in rows:
                name = str(row["name"]).strip()
                year_name = str(row["year"]).strip()
                major_types = parse_major_types(row.get("major_type", ""))

                # find subject by unique name
                stmt = await self.session.execute(
                    select(Subject).where(Subject.name == name)
                )
                subject = stmt.scalar_one_or_none()

                year = await self._get_or_create_year(year_name)

                if not subject:
                    subject_data = SubjectBase(name=name)
                    subject = Subject(
                        id=uuid4(),
                        name=subject_data.name,
                        short_name=subject_data.short_name,
                        student_year_id=year.id,
                    )
                    self.session.add(subject)
                    await self.session.flush()
                else:
                    # update year if changed
                    subject.student_year_id = year.id

                # IMPORTANT: sync majors to match CSV row exactly
                await self._set_subject_majors(subject.id, major_types)

            await self.session.commit()
            return "Subjects updated successfully from file"

        except Exception as e:
            await self.session.rollback()
            raise HTTPException(detail=str(e), status_code=500)
