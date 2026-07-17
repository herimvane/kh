from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"), nullable=True)
    score_note: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        UniqueConstraint("parent_id", "name", name="uq_departments_parent_name"),
    )

    parent: Mapped["Department | None"] = relationship(remote_side=[id])


class SystemSetting(Base):
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(String(500), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Position(Base):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(220))
    role: Mapped[str] = mapped_column(String(20), default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    identity_key: Mapped[str] = mapped_column(String(36), unique=True, index=True, default=lambda: str(uuid4()))
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"), nullable=True)
    admin_scope_department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"), nullable=True, index=True)
    position_id: Mapped[int | None] = mapped_column(ForeignKey("positions.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    department: Mapped[Department | None] = relationship(foreign_keys=[department_id])
    admin_scope_department: Mapped[Department | None] = relationship(foreign_keys=[admin_scope_department_id])
    position: Mapped[Position | None] = relationship()


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)

    user: Mapped[User] = relationship()


class ScoreOption(Base):
    __tablename__ = "score_options"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    value: Mapped[Decimal] = mapped_column(Numeric(12, 4))


class Evaluation(Base):
    __tablename__ = "evaluations"
    __table_args__ = (
        UniqueConstraint("scope_key", "year", "sequence", name="uq_evaluations_scope_year_sequence"),
        UniqueConstraint("scope_key", "open_slot", name="uq_evaluations_scope_open"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), default="")
    year: Mapped[int] = mapped_column(Integer, index=True)
    sequence: Mapped[int] = mapped_column(Integer, default=1)
    scope_key: Mapped[str] = mapped_column(String(64), default="GLOBAL", index=True)
    owner_department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True)
    owner_department_name_snapshot: Mapped[str] = mapped_column(String(120), default="全局")
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    is_open: Mapped[bool] = mapped_column(Boolean, default=False)
    open_slot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tasks_generated: Mapped[bool] = mapped_column(Boolean, default=False)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    owner_department: Mapped[Department | None] = relationship(foreign_keys=[owner_department_id])
    created_by: Mapped[User | None] = relationship(foreign_keys=[created_by_id])


class EvaluationScoreOption(Base):
    __tablename__ = "evaluation_score_options"
    __table_args__ = (UniqueConstraint("evaluation_id", "score_option_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    evaluation_id: Mapped[int] = mapped_column(ForeignKey("evaluations.id", ondelete="CASCADE"))
    score_option_id: Mapped[int] = mapped_column(ForeignKey("score_options.id"))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    option: Mapped[ScoreOption] = relationship()


class EvaluationDepartmentScoreOption(Base):
    __tablename__ = "evaluation_department_score_options"
    __table_args__ = (UniqueConstraint("evaluation_id", "score_option_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    evaluation_id: Mapped[int] = mapped_column(ForeignKey("evaluations.id", ondelete="CASCADE"))
    score_option_id: Mapped[int] = mapped_column(ForeignKey("score_options.id"))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    option: Mapped[ScoreOption] = relationship()


class EvaluationDepartmentOptionLimit(Base):
    __tablename__ = "evaluation_department_option_limits"
    __table_args__ = (UniqueConstraint("evaluation_id", "score_option_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    evaluation_id: Mapped[int] = mapped_column(ForeignKey("evaluations.id", ondelete="CASCADE"))
    score_option_id: Mapped[int] = mapped_column(ForeignKey("score_options.id"))
    max_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    option: Mapped[ScoreOption] = relationship()


class EvaluationPersonRule(Base):
    __tablename__ = "evaluation_person_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    evaluation_id: Mapped[int] = mapped_column(ForeignKey("evaluations.id", ondelete="CASCADE"))
    reviewer_position_id: Mapped[int] = mapped_column(ForeignKey("positions.id"))
    reviewer_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    target_position_id: Mapped[int] = mapped_column(ForeignKey("positions.id"))
    score_group: Mapped[str] = mapped_column(String(160), default="")
    scope_type: Mapped[str] = mapped_column(String(40), default="selected_departments")
    weight: Mapped[Decimal] = mapped_column(Numeric(12, 4))

    reviewer_position: Mapped[Position] = relationship(foreign_keys=[reviewer_position_id])
    reviewer_user: Mapped[User | None] = relationship(foreign_keys=[reviewer_user_id])
    target_position: Mapped[Position] = relationship(foreign_keys=[target_position_id])
    target_departments: Mapped[list["EvaluationPersonRuleDepartment"]] = relationship(
        cascade="all, delete-orphan",
        back_populates="rule",
    )
    option_limits: Mapped[list["EvaluationPersonRuleOptionLimit"]] = relationship(
        cascade="all, delete-orphan",
        back_populates="rule",
    )


class EvaluationPersonPositionOptionLimit(Base):
    __tablename__ = "evaluation_person_position_option_limits"
    __table_args__ = (UniqueConstraint("evaluation_id", "target_position_id", "score_option_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    evaluation_id: Mapped[int] = mapped_column(ForeignKey("evaluations.id", ondelete="CASCADE"))
    target_position_id: Mapped[int] = mapped_column(ForeignKey("positions.id"))
    score_option_id: Mapped[int] = mapped_column(ForeignKey("score_options.id"))
    max_people: Mapped[int | None] = mapped_column(Integer, nullable=True)

    target_position: Mapped[Position] = relationship()
    option: Mapped[ScoreOption] = relationship()


class EvaluationPersonRuleOptionLimit(Base):
    __tablename__ = "evaluation_person_rule_option_limits"
    __table_args__ = (UniqueConstraint("rule_id", "score_option_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("evaluation_person_rules.id", ondelete="CASCADE"))
    score_option_id: Mapped[int] = mapped_column(ForeignKey("score_options.id"))
    max_people: Mapped[int | None] = mapped_column(Integer, nullable=True)

    rule: Mapped[EvaluationPersonRule] = relationship(back_populates="option_limits")
    option: Mapped[ScoreOption] = relationship()


class EvaluationPersonRuleDepartment(Base):
    __tablename__ = "evaluation_person_rule_departments"
    __table_args__ = (UniqueConstraint("rule_id", "department_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("evaluation_person_rules.id", ondelete="CASCADE"))
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"))

    rule: Mapped[EvaluationPersonRule] = relationship(back_populates="target_departments")
    department: Mapped[Department] = relationship()


class EvaluationDepartmentRule(Base):
    __tablename__ = "evaluation_department_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    evaluation_id: Mapped[int] = mapped_column(ForeignKey("evaluations.id", ondelete="CASCADE"))
    group_key: Mapped[str] = mapped_column(String(36), default=lambda: str(uuid4()), index=True)
    reviewer_position_id: Mapped[int] = mapped_column(ForeignKey("positions.id"))
    target_department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"))
    weight: Mapped[Decimal] = mapped_column(Numeric(12, 4))

    reviewer_position: Mapped[Position] = relationship()
    target_department: Mapped[Department] = relationship()
    option_limits: Mapped[list["EvaluationDepartmentRuleOptionLimit"]] = relationship(
        cascade="all, delete-orphan",
        back_populates="rule",
    )


class EvaluationDepartmentShareRule(Base):
    __tablename__ = "evaluation_department_share_rules"
    __table_args__ = (UniqueConstraint("evaluation_id", "target_position_id", "department_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    evaluation_id: Mapped[int] = mapped_column(ForeignKey("evaluations.id", ondelete="CASCADE"))
    target_position_id: Mapped[int] = mapped_column(ForeignKey("positions.id"))
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"))
    weight: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    manual_department_score: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)

    target_position: Mapped[Position] = relationship()
    department: Mapped[Department] = relationship()


class EvaluationDepartmentScoreShareRule(Base):
    __tablename__ = "evaluation_department_score_share_rules"
    __table_args__ = (UniqueConstraint("evaluation_id", "target_position_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    evaluation_id: Mapped[int] = mapped_column(ForeignKey("evaluations.id", ondelete="CASCADE"))
    target_position_id: Mapped[int] = mapped_column(ForeignKey("positions.id"))
    weight: Mapped[Decimal] = mapped_column(Numeric(12, 4))

    target_position: Mapped[Position] = relationship()


class EvaluationDepartmentManualScore(Base):
    __tablename__ = "evaluation_department_manual_scores"
    __table_args__ = (UniqueConstraint("evaluation_id", "department_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    evaluation_id: Mapped[int] = mapped_column(ForeignKey("evaluations.id", ondelete="CASCADE"))
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"))
    score: Mapped[Decimal] = mapped_column(Numeric(12, 4))

    department: Mapped[Department] = relationship()


class EvaluationDepartmentRuleOptionLimit(Base):
    __tablename__ = "evaluation_department_rule_option_limits"
    __table_args__ = (UniqueConstraint("rule_id", "score_option_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("evaluation_department_rules.id", ondelete="CASCADE"))
    score_option_id: Mapped[int] = mapped_column(ForeignKey("score_options.id"))
    max_people: Mapped[int | None] = mapped_column(Integer, nullable=True)

    rule: Mapped[EvaluationDepartmentRule] = relationship(back_populates="option_limits")
    option: Mapped[ScoreOption] = relationship()


class EvaluationTask(Base):
    __tablename__ = "evaluation_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    evaluation_id: Mapped[int] = mapped_column(ForeignKey("evaluations.id", ondelete="CASCADE"))
    reviewer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    task_type: Mapped[str] = mapped_column(String(20))
    rule_id: Mapped[int] = mapped_column(Integer)
    weight: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    target_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    target_department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"), nullable=True)
    submitted: Mapped[bool] = mapped_column(Boolean, default=False)

    reviewer: Mapped[User] = relationship(foreign_keys=[reviewer_id])
    target_user: Mapped[User | None] = relationship(foreign_keys=[target_user_id])
    target_department: Mapped[Department | None] = relationship()


class EvaluationVote(Base):
    __tablename__ = "evaluation_votes"
    __table_args__ = (UniqueConstraint("task_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    evaluation_id: Mapped[int] = mapped_column(ForeignKey("evaluations.id", ondelete="CASCADE"))
    task_id: Mapped[int] = mapped_column(ForeignKey("evaluation_tasks.id", ondelete="CASCADE"))
    reviewer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    score_option_id: Mapped[int] = mapped_column(ForeignKey("score_options.id"))
    score_value: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    task: Mapped[EvaluationTask] = relationship()
    option: Mapped[ScoreOption] = relationship()


class EvaluationReviewReopen(Base):
    __tablename__ = "evaluation_review_reopens"
    __table_args__ = (UniqueConstraint("evaluation_id", "reviewer_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    evaluation_id: Mapped[int] = mapped_column(ForeignKey("evaluations.id", ondelete="CASCADE"))
    reviewer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    reviewer: Mapped[User] = relationship(foreign_keys=[reviewer_id])
    admin: Mapped[User] = relationship(foreign_keys=[created_by])


class ArchivedPersonScore(Base):
    __tablename__ = "archived_person_scores"

    id: Mapped[int] = mapped_column(primary_key=True)
    evaluation_id: Mapped[int] = mapped_column(ForeignKey("evaluations.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(Integer)
    username: Mapped[str] = mapped_column(String(80))
    full_name: Mapped[str] = mapped_column(String(120))
    department_name: Mapped[str] = mapped_column(String(120), default="")
    position_name: Mapped[str] = mapped_column(String(120), default="")
    final_score: Mapped[Decimal] = mapped_column(Numeric(12, 4))


class ArchivedDepartmentScore(Base):
    __tablename__ = "archived_department_scores"

    id: Mapped[int] = mapped_column(primary_key=True)
    evaluation_id: Mapped[int] = mapped_column(ForeignKey("evaluations.id", ondelete="CASCADE"))
    department_id: Mapped[int] = mapped_column(Integer)
    department_name: Mapped[str] = mapped_column(String(120))
    final_score: Mapped[Decimal] = mapped_column(Numeric(12, 4))


class ArchivedVoteDetail(Base):
    __tablename__ = "archived_vote_details"

    id: Mapped[int] = mapped_column(primary_key=True)
    evaluation_id: Mapped[int] = mapped_column(ForeignKey("evaluations.id", ondelete="CASCADE"))
    task_type: Mapped[str] = mapped_column(String(20))
    reviewer_id: Mapped[int] = mapped_column(Integer)
    reviewer_identity_key: Mapped[str] = mapped_column(String(64), default="")
    reviewer_name: Mapped[str] = mapped_column(String(120))
    target_id: Mapped[int] = mapped_column(Integer)
    target_name: Mapped[str] = mapped_column(String(120))
    target_department_name: Mapped[str] = mapped_column(String(120), default="")
    target_position_name: Mapped[str] = mapped_column(String(120), default="")
    option_name: Mapped[str] = mapped_column(String(80))
    score_value: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    weight: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    weighted_score: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    rule_label: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ArchivedSubmission(Base):
    __tablename__ = "archived_submissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    evaluation_id: Mapped[int] = mapped_column(ForeignKey("evaluations.id", ondelete="CASCADE"))
    reviewer_id: Mapped[int] = mapped_column(Integer)
    reviewer_identity_key: Mapped[str] = mapped_column(String(64), default="", index=True)
    reviewer_name: Mapped[str] = mapped_column(String(120))
    reviewer_department_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    department_name: Mapped[str] = mapped_column(String(120), default="")
    position_name: Mapped[str] = mapped_column(String(120), default="")
    task_count: Mapped[int] = mapped_column(Integer)
    submitted_count: Mapped[int] = mapped_column(Integer)
    status_label: Mapped[str] = mapped_column(String(40), default="已提交")
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ArchivedRuleSnapshot(Base):
    __tablename__ = "archived_rule_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    evaluation_id: Mapped[int] = mapped_column(ForeignKey("evaluations.id", ondelete="CASCADE"))
    snapshot_type: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(160))
    payload: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class EvaluationAuditLog(Base):
    __tablename__ = "evaluation_audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    evaluation_id: Mapped[int] = mapped_column(ForeignKey("evaluations.id", ondelete="CASCADE"))
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actor_name: Mapped[str] = mapped_column(String(120), default="")
    action: Mapped[str] = mapped_column(String(80))
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
