"""
Agent baseline configuration for handling account resets.

Each agent has a baselineStartIso (ISO timestamp when account was reset) and baselineEquity
(the equity value after reset - THIS VARIES BY ACCOUNT, NOT ALL ARE 100k).

IMPORTANT:
- Each project uses its own Alpaca account with its own API keys
- Each account may have a different starting equity after reset (e.g., 100k, 50k, 25k, etc.)
- baselineEquity is ONLY used for Total P&L calculation: currentEquity - baselineEquity
- Week/Month P&L calculations use ACTUAL equity points from account history, NOT baselineEquity
- Day/Week/Month metrics are computed from the account's own portfolio history

All metrics are computed ONLY from baselineStartIso forward.
"""

# Agent baseline configurations
# Format: project_number: {baselineStartIso, baselineEquity}
# 
# CRITICAL: Set baselineEquity to the ACTUAL equity value after reset for EACH account.
# This value is used ONLY for Total P&L calculation. Week/Month use actual history points.
AGENT_BASELINES = {
    1: {  # Swing Trading Agent (Stocks) - Uses ALPACA_API_KEY / ALPACA_SECRET_KEY
        'baselineStartIso': '2024-01-01T00:00:00Z',  # ISO timestamp when Project 1 account was reset
        'baselineEquity': 10000.0  # Fallback only - actual value fetched from API (Project 1 started at 10k)
    },
    2: {  # Coin Trading Agent (Crypto) - Uses ALPACA_API_KEY_2 / ALPACA_SECRET_KEY_2
        'baselineStartIso': '2024-01-01T00:00:00Z',  # ISO timestamp when Project 2 account was reset
        'baselineEquity': 10000.0  # Fallback only - actual value fetched from API (Project 2 started at 10k)
    }
}


def get_baseline(project):
    """Get baseline configuration for a project."""
    return AGENT_BASELINES.get(project, {
        'baselineStartIso': '2024-01-01T00:00:00Z',
        'baselineEquity': 100000.0
    })


def get_baseline_start_datetime(project):
    """Get baseline start as datetime object."""
    from datetime import datetime, timezone
    baseline = get_baseline(project)
    baseline_iso = baseline['baselineStartIso']
    try:
        # Parse ISO format
        if baseline_iso.endswith('Z'):
            baseline_iso = baseline_iso[:-1] + '+00:00'
        return datetime.fromisoformat(baseline_iso).replace(tzinfo=timezone.utc)
    except Exception as e:
        print(f"Error parsing baselineStartIso for project {project}: {e}")
        # Default to a very old date if parsing fails
        return datetime(2020, 1, 1, tzinfo=timezone.utc)
