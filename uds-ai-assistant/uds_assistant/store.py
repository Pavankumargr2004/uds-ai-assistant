"""Structured storage for projects, profiles, test cases, runs and audit events using SQLAlchemy."""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import create_engine, Column, String, Float, JSON
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import Settings
from .generator.models import TestCase
from .protocol.profile import ECUProfile
from .runner.runner import RunSummary


class AuditEvent(BaseModel):
    ts: float = Field(default_factory=time.time)
    user: str
    role: str
    action: str
    detail: str = ""


class Review(BaseModel):
    ts: float = Field(default_factory=time.time)
    user: str
    decision: str  # approved | rejected | changes_requested
    comment: str = ""


class ProjectState(BaseModel):
    name: str
    created_ts: float = Field(default_factory=time.time)
    profile: Optional[dict] = None
    profile_source: str = ""
    tests: dict[str, dict] = Field(default_factory=dict)
    reviews: dict[str, list[dict]] = Field(default_factory=dict)
    runs: list[dict] = Field(default_factory=list)
    audit: list[dict] = Field(default_factory=list)


Base = declarative_base()

class DBProjectState(Base):
    __tablename__ = "projects"
    name = Column(String, primary_key=True)
    created_ts = Column(Float, nullable=False, default=time.time)
    profile = Column(JSON, nullable=True)
    profile_source = Column(String, default="")
    tests = Column(JSON, default=dict)
    reviews = Column(JSON, default=dict)
    runs = Column(JSON, default=list)
    audit = Column(JSON, default=list)


class ProjectStore:
    def __init__(self, settings: Settings):
        self.s = settings
        self._locks: dict[str, threading.Lock] = {}
        
        self.s.projects_dir.mkdir(parents=True, exist_ok=True)
        
        db_url = os.environ.get("DATABASE_URL")
        if not db_url:
            db_path = self.s.projects_dir / "db.sqlite3"
            db_url = f"sqlite:///{db_path.absolute().as_posix()}"
            
        self.engine = create_engine(db_url)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)

    def _lock(self, project: str) -> threading.Lock:
        return self._locks.setdefault(project, threading.Lock())

    def list_projects(self) -> list[str]:
        with self.SessionLocal() as session:
            projects = session.query(DBProjectState.name).all()
            return sorted(p[0] for p in projects)

    def exists(self, project: str) -> bool:
        with self.SessionLocal() as session:
            return session.query(DBProjectState).filter_by(name=project).first() is not None

    def load(self, project: str) -> ProjectState:
        with self.SessionLocal() as session:
            db_obj = session.query(DBProjectState).filter_by(name=project).first()
            if not db_obj:
                raise FileNotFoundError(f"project {project!r} does not exist")
            
            return ProjectState(
                name=db_obj.name,
                created_ts=db_obj.created_ts,
                profile=db_obj.profile,
                profile_source=db_obj.profile_source,
                tests=db_obj.tests or {},
                reviews=db_obj.reviews or {},
                runs=db_obj.runs or [],
                audit=db_obj.audit or []
            )

    def save(self, state: ProjectState) -> None:
        with self.SessionLocal() as session:
            db_obj = session.query(DBProjectState).filter_by(name=state.name).first()
            if not db_obj:
                db_obj = DBProjectState(name=state.name)
                session.add(db_obj)
            
            db_obj.created_ts = state.created_ts
            db_obj.profile = state.profile
            db_obj.profile_source = state.profile_source
            db_obj.tests = state.tests
            db_obj.reviews = state.reviews
            db_obj.runs = state.runs
            db_obj.audit = state.audit
            
            session.commit()

    def create(self, project: str) -> ProjectState:
        if self.exists(project):
            raise FileExistsError(f"project {project!r} already exists")
        st = ProjectState(name=project)
        self.save(st)
        return st

    # -- higher-level, lock-protected mutators -------------------------------------------------
    def audit(self, project: str, user: str, role: str, action: str, detail: str = "") -> None:
        with self._lock(project):
            st = self.load(project)
            st.audit.append(AuditEvent(user=user, role=role, action=action, detail=detail).model_dump())
            self.save(st)

    def set_profile(self, project: str, profile: ECUProfile, source: str, user: str, role: str) -> None:
        with self._lock(project):
            st = self.load(project)
            st.profile, st.profile_source = profile.model_dump(mode="json"), source
            st.audit.append(AuditEvent(user=user, role=role, action="set_profile",
                                       detail=f"{profile.name} v{profile.version} from {source}").model_dump())
            self.save(st)

    def get_profile(self, project: str) -> Optional[ECUProfile]:
        st = self.load(project)
        return ECUProfile.model_validate(st.profile) if st.profile else None

    def save_tests(self, project: str, tests: list[TestCase], user: str, role: str, origin: str) -> None:
        with self._lock(project):
            st = self.load(project)
            for t in tests:
                st.tests[t.id] = t.model_dump(mode="json")
            st.audit.append(AuditEvent(user=user, role=role, action="generate_tests",
                                       detail=f"{len(tests)} test(s) via {origin}").model_dump())
            self.save(st)

    def list_tests(self, project: str) -> list[TestCase]:
        st = self.load(project)
        return [TestCase.model_validate(v) for v in st.tests.values()]

    def get_test(self, project: str, test_id: str) -> Optional[TestCase]:
        st = self.load(project)
        v = st.tests.get(test_id)
        return TestCase.model_validate(v) if v else None

    def update_test(self, project: str, test: TestCase, user: str, role: str, action: str = "edit_test") -> None:
        with self._lock(project):
            st = self.load(project)
            if test.id not in st.tests:
                raise KeyError(test.id)
            st.tests[test.id] = test.model_dump(mode="json")
            st.audit.append(AuditEvent(user=user, role=role, action=action, detail=test.id).model_dump())
            self.save(st)

    def review_test(self, project: str, test_id: str, user: str, role: str, decision: str, comment: str,
                    four_eyes: bool) -> TestCase:
        with self._lock(project):
            st = self.load(project)
            if test_id not in st.tests:
                raise KeyError(test_id)
            tc = TestCase.model_validate(st.tests[test_id])
            if four_eyes and decision == "approved" and tc.created_by and tc.created_by == user:
                raise PermissionError("four-eyes review is enabled: the approver must differ from the test author")
            st.reviews.setdefault(test_id, []).append(Review(user=user, decision=decision, comment=comment).model_dump())
            if decision == "approved":
                tc.status = "approved"
            elif decision == "rejected":
                tc.status = "rejected"
            else:
                tc.status = "draft"
            st.tests[test_id] = tc.model_dump(mode="json")
            st.audit.append(AuditEvent(user=user, role=role, action=f"review_{decision}", detail=test_id).model_dump())
            self.save(st)
            return tc

    def record_run(self, project: str, summary: RunSummary, user: str, role: str,
                   test_ids: list[str]) -> dict:
        with self._lock(project):
            st = self.load(project)
            entry = {"run_id": uuid.uuid4().hex[:12], "ts": time.time(), "user": user,
                     "summary": summary.model_dump(mode="json"), "test_ids": test_ids}
            st.runs.append(entry)
            st.audit.append(AuditEvent(user=user, role=role, action="run_tests",
                                       detail=f"{summary.target}: {summary.passed}/{summary.total} passed").model_dump())
            self.save(st)
            return entry

    def list_runs(self, project: str) -> list[dict]:
        return self.load(project).runs

    def audit_log(self, project: str) -> list[dict]:
        return self.load(project).audit
