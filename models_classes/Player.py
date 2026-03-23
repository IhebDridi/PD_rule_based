"""
Player field patterns and helpers live in each app's ``models.py`` (oTree ``Player`` cannot
subclass a mapped ``BasePlayer`` from another package). Optional copy-paste helpers:

    def get_agent_decision_mandatory(player, round_number):
        field_name = f"agent_decision_mandatory_delegation_round_{round_number}"
        value = player.field_maybe_none(field_name)
        return value if value is not None else None
"""
