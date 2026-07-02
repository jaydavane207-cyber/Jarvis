from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.modules.productivity.models import Task
from app.modules.productivity.schemas import TaskCreate, TaskResponse

def determine_quadrant(is_urgent: bool, is_important: bool) -> str:
    if is_urgent and is_important:
        return "Q1: Do First"
    elif not is_urgent and is_important:
        return "Q2: Schedule"
    elif is_urgent and not is_important:
        return "Q3: Delegate"
    else:
        return "Q4: Eliminate"

def to_response(task: Task) -> TaskResponse:
    return TaskResponse(
        id=task.id,
        title=task.title,
        description=task.description,
        due_date=task.due_date,
        is_urgent=task.is_urgent,
        is_important=task.is_important,
        is_completed=task.is_completed,
        created_at=task.created_at,
        eisenhower_quadrant=determine_quadrant(task.is_urgent, task.is_important)
    )

async def create_task(db: AsyncSession, task_in: TaskCreate) -> TaskResponse:
    db_task = Task(
        title=task_in.title,
        description=task_in.description,
        due_date=task_in.due_date,
        is_urgent=task_in.is_urgent,
        is_important=task_in.is_important
    )
    db.add(db_task)
    await db.commit()
    await db.refresh(db_task)
    return to_response(db_task)

async def get_tasks(db: AsyncSession):
    result = await db.execute(select(Task).order_by(Task.is_completed, Task.due_date))
    tasks = result.scalars().all()
    return [to_response(t) for t in tasks]
