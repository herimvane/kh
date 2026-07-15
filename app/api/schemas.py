from pydantic import BaseModel


class Pagination(BaseModel):
    page: int
    total_pages: int
    total: int
    page_size: int


class UserSummary(BaseModel):
    id: int
    username: str
    full_name: str
    role: str
    is_active: bool
    must_change_password: bool = False
    department_id: int | None = None
    position_id: int | None = None


class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class LoginResponse(BaseModel):
    user: UserSummary
    redirect_to: str


class MessageResponse(BaseModel):
    message: str


class ScoreDetailPasswordRequest(BaseModel):
    password: str


class DepartmentCreate(BaseModel):
    name: str
    parent_id: int | None = None
    sort_order: int | None = None


class DepartmentUpdate(DepartmentCreate):
    pass


class DepartmentRow(BaseModel):
    id: int
    name: str
    parent_id: int | None = None
    parent_name: str | None = None
    sort_order: int


class DepartmentChoice(DepartmentRow):
    depth: int
    display_name: str
    has_children: bool


class PositionCreate(BaseModel):
    name: str
    sort_order: int | None = None


class PositionUpdate(PositionCreate):
    pass


class PositionRow(BaseModel):
    id: int
    name: str
    sort_order: int


class ReviewerUserRow(BaseModel):
    id: int
    name: str
    department_name: str | None = None


class UserCreate(BaseModel):
    username: str
    full_name: str
    password: str = "password!"
    role: str = "user"
    department_id: int | None = None
    position_id: int | None = None


class UserUpdate(BaseModel):
    username: str
    full_name: str
    role: str = "user"
    is_active: bool = True
    department_id: int | None = None
    position_id: int | None = None
    password: str = ""


class UserRow(BaseModel):
    id: int
    username: str
    full_name: str
    role: str
    is_active: bool
    must_change_password: bool = False
    department_id: int | None = None
    position_id: int | None = None
    department_name: str | None = None
    position_name: str | None = None


class UserListResponse(BaseModel):
    items: list[UserRow]
    pagination: Pagination


class ScoreOptionCreate(BaseModel):
    name: str
    value: float


class ScoreOptionUpdate(ScoreOptionCreate):
    pass


class ScoreOptionRow(BaseModel):
    id: int
    name: str
    value: float


class EvaluationCreate(BaseModel):
    year: int
    name: str = ""


class EvaluationRow(BaseModel):
    id: int
    name: str
    year: int
    is_open: bool
    tasks_generated: bool
    archived: bool
    total_tasks: int = 0
    submitted_tasks: int = 0
    pending_reopens: int = 0


class EvaluationActionResponse(BaseModel):
    message: str
    evaluation: EvaluationRow | None = None


class VoteSubmitRequest(BaseModel):
    choices: dict[int, int]
