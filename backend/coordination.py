"""Approval-gated task tracking for a local demonstration; no agency dispatch."""

from datetime import datetime, timezone

from .schemas import ActionEvent, ActionStatus, ProposedAction, RiskProfile, TaskStatus


def _action(profile: RiskProfile, action_id: str) -> ProposedAction:
    action = next((item for item in profile.proposed_actions if item.action_id == action_id), None)
    if action is None:
        raise ValueError(f"Unknown action: {action_id}")
    if action.status != ActionStatus.APPROVED:
        raise ValueError("Human approval is required before task coordination")
    return action


def _record(profile: RiskProfile, action: ProposedAction, event: str, actor: str, now: datetime, note: str) -> None:
    profile.action_history.append(ActionEvent(
        action_id=action.action_id, event=event, actor=actor.strip(), recorded_at=now, note=note,
    ))
    report = next((item for item in profile.agent_functions if item.role_id == "coordination"), None)
    if report is not None:
        completed = sum(item.task_status == TaskStatus.COMPLETED for item in profile.proposed_actions)
        report.summary = f"Local task tracking: {completed}/{len(profile.proposed_actions)} completed. No agency notification has been sent."
        if completed == len(profile.proposed_actions):
            report.status = "completed"


def assign_action(profile: RiskProfile, action_id: str, *, actor: str, due_at: datetime) -> RiskProfile:
    """Assign to the proposal's scoped owner only after prerequisites are complete."""

    action = _action(profile, action_id)
    now = datetime.now(timezone.utc)
    if not actor.strip():
        raise ValueError("A coordinator label is required")
    if due_at.tzinfo is None or due_at.utcoffset() is None or due_at <= now:
        raise ValueError("The deadline must be timezone-aware and in the future")
    if action.task_status != TaskStatus.UNASSIGNED:
        raise ValueError("Only an unassigned task can be assigned")
    actions = {item.action_id: item for item in profile.proposed_actions}
    if any(dependency not in actions or actions[dependency].task_status != TaskStatus.COMPLETED
           for dependency in action.depends_on):
        raise ValueError("Complete all prerequisite tasks before assigning this task")
    action.task_status = TaskStatus.ASSIGNED
    action.assigned_at = now
    action.due_at = due_at
    _record(profile, action, "assigned", actor, now, f"Assigned locally to {action.owner}; due {due_at.isoformat()}.")
    return profile


def acknowledge_action(profile: RiskProfile, action_id: str, *, actor: str) -> RiskProfile:
    action = _action(profile, action_id)
    if not actor.strip():
        raise ValueError("An acknowledging person label is required")
    if action.task_status != TaskStatus.ASSIGNED:
        raise ValueError("Only an assigned task can be acknowledged")
    now = datetime.now(timezone.utc)
    action.task_status = TaskStatus.ACKNOWLEDGED
    action.acknowledged_at = now
    _record(profile, action, "acknowledged", actor, now, "Acknowledgement recorded locally with a self-reported identity.")
    return profile


def complete_action(profile: RiskProfile, action_id: str, *, actor: str, result: str) -> RiskProfile:
    action = _action(profile, action_id)
    if not actor.strip() or not result.strip():
        raise ValueError("Record who supplied the outcome and a result, including unavailable or inconclusive findings")
    if action.task_status != TaskStatus.ACKNOWLEDGED:
        raise ValueError("Acknowledge the task before recording completion")
    now = datetime.now(timezone.utc)
    action.task_status = TaskStatus.COMPLETED
    action.completed_at = now
    action.result = result.strip()
    _record(profile, action, "completed", actor, now, result.strip())
    return profile
