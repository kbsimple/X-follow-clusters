"""Automation mode offer and registry update.

Per REVIEW-07 and D-05: After AUTOMATION_ROUNDS (default=2) approved rounds,
offer to enable full automation mode for future review sessions.
When enabled, Phase 6 skips interactive review and uses all approved clusters directly.
"""
import questionary
from rich.console import Console
from src.review.registry import ApprovalRegistry, save_registry, AUTOMATION_ROUNDS

console = Console()


def should_offer_automation(reg: ApprovalRegistry) -> bool:
    """Return True if automation offer should be presented.

    Conditions:
    - rounds_completed >= AUTOMATION_ROUNDS
    - automation_offered == False (not yet offered this session)
    """
    return reg.rounds_completed >= AUTOMATION_ROUNDS and not reg.automation_offered


def offer_automation_mode(reg: ApprovalRegistry) -> ApprovalRegistry:
    """Present automation offer to user via questionary prompt.

    Per REVIEW-07: After N approved rounds (configurable), offer to enable full automation.
    D-05: After 2 approved rounds, offer full automation mode.

    Options:
    - "Enable automation" — set automation_enabled=True in registry
    - "Keep manual review" — set automation_offered=True but automation_enabled=False
    - "Skip" — same as keep manual (no change)

    Returns:
        Updated registry with automation_offered=True (and possibly automation_enabled=True).
    """
    if not should_offer_automation(reg):
        return reg

    console.print(f"\n[bold green]Milestone: {reg.rounds_completed} approval rounds completed![/bold green]")
    console.print(
        f"[yellow]You are now eligible for [bold]full automation mode[/bold].\n"
        f"When enabled, Phase 6 will create X API lists for all approved clusters "
        f"without further interactive review.[/yellow]\n"
    )

    choice = questionary.select(
        f"Enable full automation after {reg.rounds_completed} successful rounds?",
        choices=[
            "Enable automation — skip review in future sessions",
            "Keep manual review — ask me each time",
        ],
    ).ask()

    if choice and "Enable" in choice:
        reg.automation_enabled = True
        console.print("[green]Automation enabled. Future sessions will skip interactive review.[/green]")
    else:
        console.print("[dim]Keeping manual review mode.[/dim]")

    reg.automation_offered = True
    save_registry(reg)
    return reg


def is_automation_enabled(reg: ApprovalRegistry) -> bool:
    """Check if automation mode is active (for Phase 6 to read)."""
    return reg.automation_enabled